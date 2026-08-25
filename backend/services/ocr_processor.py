"""OCR 批量处理服务

封装 PaddleOCR API 调用，支持：
- 单文件 OCR 处理
- 目录批量遍历处理（ThreadPoolExecutor 并发，可调 max_workers）
- 与 knowledge_api 状态联动（pending → processing → indexed/failed）

安全注意：OCR API 应限制访问（内网或鉴权），当前部署在内网，
外网不可直接访问。若迁移到公网，务必增加鉴权机制。
"""

import base64
import io
import logging
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

# OCR API 地址由环境变量 PADDLE_OCR_API_URL 提供；未配置时 OCR 功能不可用。
# 不提供默认地址：历史版本的内置地址属于内部基础设施，不应随开源版本分发，
# 且向不可控端点发送用户文档存在数据外泄风险。
MAX_OCR_FILE_SIZE = 50 * 1024 * 1024


class OcrProcessor:
    """OCR 批量处理服务"""

    # 配置常量
    PADDLE_OCR_API_URL = os.environ.get("PADDLE_OCR_API_URL", "")
    BATCH_SIZE = 10   # PDF 分批页数
    TIMEOUT = 300      # API 超时秒数
    # 并发数：需根据 OCR API 限流策略调整，当前默认 4
    MAX_WORKERS = int(os.environ.get("OCR_MAX_WORKERS", "4"))

    def __init__(self, db_session=None):
        """
        Args:
            db_session: SQLAlchemy session（用于状态联动）
        """
        self.db_session = db_session

    # === 核心方法 ===

    # 支持的图片扩展名
    IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}

    # Office 文档扩展名（走 DocumentProcessor，不走 OCR API）
    OFFICE_EXTENSIONS = {'.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt'}

    def process_file(self, file_path: str, output_dir: str) -> dict:
        """
        处理单个文件（PDF 或图片）

        Args:
            file_path: 输入文件路径
            output_dir: 输出目录

        Returns:
            {
                'success': bool,
                'pages': int,
                'markdown_files': list[str],  # 生成的 .md 文件路径
                'error': str | None
            }
        """
        if not os.path.exists(file_path):
            return {
                'success': False,
                'pages': 0,
                'markdown_files': [],
                'error': 'File not found'
            }

        # 文件大小检查：防止超大文件 base64 编码后 OOM
        file_size = os.path.getsize(file_path)
        if file_size > MAX_OCR_FILE_SIZE:
            return {
                'success': False,
                'pages': 0,
                'markdown_files': [],
                'error': f'File too large for OCR: {file_size} bytes (limit {MAX_OCR_FILE_SIZE})'
            }

        ext = Path(file_path).suffix.lower()
        is_pdf = ext == '.pdf'
        is_image = ext in self.IMAGE_EXTENSIONS

        if not is_pdf and not is_image:
            return {
                'success': False,
                'pages': 0,
                'markdown_files': [],
                'error': f'Unsupported file type: {ext}, only PDF and images are supported'
            }

        try:
            results = self._process_pdf(file_path) if is_pdf else self._process_image(file_path)
            markdown_files = self._save_results(results, output_dir)

            return {
                'success': True,
                'pages': len(results),
                'markdown_files': markdown_files,
                'error': None
            }

        except requests.Timeout:
            return {
                'success': False,
                'pages': 0,
                'markdown_files': [],
                'error': 'OCR API timeout'
            }
        except RuntimeError as e:
            return {
                'success': False,
                'pages': 0,
                'markdown_files': [],
                'error': str(e)
            }
        except Exception as e:
            logger.exception(f'OCR processing failed: {file_path}')
            return {
                'success': False,
                'pages': 0,
                'markdown_files': [],
                'error': f'OCR processing failed: {str(e)}'
            }

    def process_directory(self, dir_path: str, output_dir: str) -> dict:
        """
        批量处理目录下所有 PDF

        Args:
            dir_path: 输入目录
            output_dir: 输出目录

        Returns:
            {
                'total_files': int,
                'success_count': int,
                'failed_count': int,
                'results': list[dict]  # 每个文件的处理结果
            }
        """
        # 验证目录存在
        if not os.path.isdir(dir_path):
            return {
                'total_files': 0,
                'success_count': 0,
                'failed_count': 0,
                'results': []
            }

        # 遍历 PDF 文件
        pdf_files = list(Path(dir_path).glob('*.pdf'))
        if not pdf_files:
            return {
                'total_files': 0,
                'success_count': 0,
                'failed_count': 0,
                'results': []
            }

        results = []
        # 并发处理 PDF 文件（并发数需根据 OCR API 限流策略调整）
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            future_map = {}
            for pdf_file in pdf_files:
                file_output_dir = os.path.join(output_dir, pdf_file.stem)
                future = executor.submit(self.process_file, str(pdf_file), file_output_dir)
                future_map[future] = pdf_file

            for future in as_completed(future_map):
                pdf_file = future_map[future]
                try:
                    result = future.result()
                except Exception as e:
                    logger.exception(f"process_directory worker failed: {pdf_file}")
                    result = {'success': False, 'pages': 0, 'markdown_files': [], 'error': str(e)}
                result['filename'] = pdf_file.name
                results.append(result)

        success_count = sum(1 for r in results if r['success'])
        failed_count = len(results) - success_count

        return {
            'total_files': len(pdf_files),
            'success_count': success_count,
            'failed_count': failed_count,
            'results': results
        }

    def process_knowledge_document(self, doc_id: int) -> dict:
        """
        处理 KnowledgeDocument（状态联动）

        流程：
        1. 读取 KnowledgeDocument，获取 original_path
        2. 更新 status='processing'
        3. 调用 process_file 生成 Markdown
        4. 更新 markdown_path + status='indexed'（成功）或 'failed'（失败）

        Args:
            doc_id: KnowledgeDocument ID

        Returns:
            {'success': bool, 'markdown_path': str | None, 'error': str | None}
        """
        if not self.db_session:
            return {
                'success': False,
                'markdown_path': None,
                'error': 'DB session not provided'
            }

        from models import KnowledgeDocument

        # 读取文档记录
        doc = self.db_session.get(KnowledgeDocument, doc_id)
        if not doc:
            return {
                'success': False,
                'markdown_path': None,
                'error': 'Document not found'
            }

        # 验证原始文件存在
        if not doc.original_path or not os.path.exists(doc.original_path):
            doc.status = 'failed'
            doc.ocr_error = 'Original file not found'
            doc.ocr_processed_at = datetime.now(timezone.utc)
            self.db_session.commit()
            return {
                'success': False,
                'markdown_path': None,
                'error': 'Original file not found'
            }

        # 更新状态为 processing
        doc.status = 'processing'
        self.db_session.commit()

        # 计算输出目录
        doc_dir = Path(doc.original_path).parent.parent  # documents/{doc_id}/
        markdown_dir = doc_dir / 'markdown'
        markdown_dir.mkdir(parents=True, exist_ok=True)

        try:
            ext = Path(doc.original_path).suffix.lower()

            # Office 文档：走 DocumentProcessor 提取文本，不走 OCR API
            if ext in self.OFFICE_EXTENSIONS:
                return self._process_office_document(doc, markdown_dir)

            # 执行 OCR（PDF / 图片）
            result = self.process_file(doc.original_path, str(markdown_dir))

            if result['success']:
                # 更新成功状态
                doc.markdown_path = str(markdown_dir)
                doc.status = 'indexed'
                doc.ocr_error = None
                doc.ocr_processed_at = datetime.now(timezone.utc)
                self.db_session.commit()

                return {
                    'success': True,
                    'markdown_path': str(markdown_dir),
                    'error': None,
                    'pages': result['pages'],
                    'markdown_files': result['markdown_files']
                }
            else:
                # 更新失败状态
                doc.status = 'failed'
                doc.ocr_error = result['error']
                doc.ocr_processed_at = datetime.now(timezone.utc)
                self.db_session.commit()

                return {
                    'success': False,
                    'markdown_path': None,
                    'error': result['error']
                }

        except Exception as e:
            # 异常时更新失败状态
            logger.exception(f'OCR processing failed for document {doc_id}')
            doc.status = 'failed'
            doc.ocr_error = str(e)
            doc.ocr_processed_at = datetime.now(timezone.utc)
            self.db_session.commit()

            return {
                'success': False,
                'markdown_path': None,
                'error': str(e)
            }

    def _process_office_document(self, doc, markdown_dir: Path) -> dict:
        """
        处理 Office 文档（.docx, .xlsx, .pptx 等）

        使用 DocumentProcessor 提取文本，生成与 OCR 相同结构的 Markdown 目录，
        使后续 Graphify 流程无需感知差异。

        Args:
            doc: KnowledgeDocument ORM 对象
            markdown_dir: Markdown 输出目录

        Returns:
            {'success': bool, 'markdown_path': str | None, 'error': str | None}
        """
        from services.document_processor import DocumentProcessor

        try:
            result = DocumentProcessor.process_document_from_path(
                doc.filename, doc.original_path
            )

            if not result.get('success'):
                error_msg = result.get('error', 'DocumentProcessor failed')
                doc.status = 'failed'
                doc.ocr_error = error_msg
                doc.ocr_processed_at = datetime.now(timezone.utc)
                self.db_session.commit()
                return {'success': False, 'markdown_path': None, 'error': error_msg}

            # 生成与 OCR 相同的目录结构：markdown/page_0001/doc.md
            page_dir = markdown_dir / 'page_0001'
            page_dir.mkdir(parents=True, exist_ok=True)
            md_text = result.get('text', '')
            (page_dir / 'doc.md').write_text(md_text, encoding='utf-8')

            doc.markdown_path = str(markdown_dir)
            doc.status = 'indexed'
            doc.ocr_error = None
            doc.ocr_processed_at = datetime.now(timezone.utc)
            self.db_session.commit()

            logger.info(f'Office document processed: doc_id={doc.id}, chars={len(md_text)}')
            return {
                'success': True,
                'markdown_path': str(markdown_dir),
                'error': None,
                'pages': 1,
                'markdown_files': [str(page_dir / 'doc.md')]
            }

        except Exception as e:
            logger.exception(f'Office document processing failed: doc_id={doc.id}')
            doc.status = 'failed'
            doc.ocr_error = str(e)
            doc.ocr_processed_at = datetime.now(timezone.utc)
            self.db_session.commit()
            return {'success': False, 'markdown_path': None, 'error': str(e)}

    # === 内部方法 ===

    def _call_api(self, file_base64: str, is_pdf: bool) -> dict:
        """
        调用 PaddleOCR API

        Args:
            file_base64: Base64 编码的文件内容
            is_pdf: 是否为 PDF 文件

        Returns:
            API 返回的 result 字段

        Raises:
            RuntimeError: API 返回错误
            requests.Timeout: API 超时
        """
        payload = {
            "file": file_base64,
            "fileType": 0 if is_pdf else 1,
            "restructurePages": False,
            "prettifyMarkdown": True,
        }

        if not self.PADDLE_OCR_API_URL:
            raise RuntimeError(
                "OCR 服务地址未配置：请设置环境变量 PADDLE_OCR_API_URL "
                "（指向 PaddleOCR layout-parsing 服务）后重试"
            )

        resp = requests.post(
            self.PADDLE_OCR_API_URL,
            json=payload,
            timeout=self.TIMEOUT
        )
        resp.raise_for_status()

        result = resp.json()
        if result.get("errorCode") != 0:
            raise RuntimeError(f"OCR API error: {result.get('errorMsg')}")

        return result

    def _process_pdf(self, pdf_path: str) -> list:
        """
        处理 PDF 文件（分批调用 API）

        Args:
            pdf_path: PDF 文件路径

        Returns:
            list of (page_num, layout_result) tuples
        """
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        logger.info(f"PDF {pdf_path} has {total_pages} pages, batch size={self.BATCH_SIZE}")

        all_results = []
        for start in range(0, total_pages, self.BATCH_SIZE):
            # 创建当前批次 PDF
            writer = PdfWriter()
            for i in range(start, min(start + self.BATCH_SIZE, total_pages)):
                writer.add_page(reader.pages[i])

            buf = io.BytesIO()
            writer.write(buf)
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode()

            logger.info(f"  Processing pages {start + 1}-{min(start + self.BATCH_SIZE, total_pages)}...")
            result = self._call_api(b64, is_pdf=True)

            # 提取每页结果
            for idx, lr in enumerate(result["result"]["layoutParsingResults"]):
                all_results.append((start + idx + 1, lr))

        return all_results

    def _process_image(self, image_path: str) -> list:
        """
        处理图片文件（调用 PaddleOCR API，fileType=1）

        Args:
            image_path: 图片文件路径

        Returns:
            list of (page_num, layout_result) tuples，图片固定为单页 [(1, lr)]
        """
        with open(image_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()

        logger.info(f"Processing image: {image_path}")
        result = self._call_api(b64, is_pdf=False)

        layout_results = result.get("result", {}).get("layoutParsingResults", [])
        if not layout_results:
            raise RuntimeError(f"OCR API returned empty result for image: {image_path}")

        return [(1, layout_results[0])]

    def _html_table_to_md(self, html: str) -> str:
        """
        将 HTML <table> 转为 Markdown 表格

        Args:
            html: HTML 表格字符串

        Returns:
            Markdown 表格字符串
        """
        rows = re.findall(r"<tr>(.*?)</tr>", html, re.S)
        if not rows:
            return html

        md_rows = []
        for row in rows:
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            md_rows.append("| " + " | ".join(cells) + " |")

        if len(md_rows) < 1:
            return html

        # 在表头后插入分隔行
        cols = len(md_rows[0].split("|")) - 2
        separator = "| " + " | ".join(["---"] * max(cols, 1)) + " |"
        md_rows.insert(1, separator)

        return "\n".join(md_rows)

    def _to_simple_md(self, md_text: str) -> str:
        """
        将带 HTML 语法的 Markdown 转为纯 Markdown

        Args:
            md_text: 带 HTML 语法的 Markdown 文本

        Returns:
            纯 Markdown 文本
        """
        text = md_text

        # 1. HTML 表格 → Markdown 表格
        text = re.sub(
            r"<table[^>]*>.*?</table>",
            lambda m: self._html_table_to_md(m.group()),
            text,
            flags=re.S,
        )

        # 2. <img> → ![alt](src)
        text = re.sub(
            r'<img[^>]*src=["\']([^"\']+)["\'][^>]*alt=["\']([^"\']*)["\'][^>]*/?>',
            r"![\2](\1)",
            text,
            flags=re.I,
        )
        text = re.sub(
            r'<img[^>]*alt=["\']([^"\']*)["\'][^>]*src=["\']([^"\']+)["\'][^>]*/?>',
            r"![\1](\2)",
            text,
            flags=re.I,
        )
        text = re.sub(r'<img[^>]*src=["\']([^"\']+)["\'][^>]*/?>', r"![](\1)", text, flags=re.I)

        # 3. 移除容器标签
        text = re.sub(
            r"</?(?:div|span|section|article|aside|header|footer|main|nav|figure|figcaption)[^>]*>",
            "",
            text,
        )

        # 4. <br> → 换行
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)

        # 5. 移除行内格式标签
        text = re.sub(
            r"</?(?:b|strong|i|em|u|s|del|sup|sub|small|big|code|mark|p)[^>]*>",
            "",
            text,
            flags=re.I,
        )

        # 6. 清理多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def _save_results(self, results: list, output_dir: str) -> list:
        """
        保存 OCR 结果到 Markdown 文件

        Args:
            results: list of (page_num, layout_result) tuples
            output_dir: 输出目录

        Returns:
            生成的 .md 文件路径列表
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        markdown_files = []
        for page_num, lr in results:
            page_dir = output_path / f"page_{page_num:04d}"
            page_dir.mkdir(parents=True, exist_ok=True)

            # 完整 MD（含 HTML 表格语法）
            md_text = lr.get("markdown", {}).get("text", "")
            if md_text:
                (page_dir / "doc.md").write_text(md_text, encoding="utf-8")

            # 简洁 MD（纯 Markdown 语法）
            simple_md = self._to_simple_md(md_text)
            simple_path = page_dir / "doc_simple.md"
            simple_path.write_text(simple_md, encoding="utf-8")
            markdown_files.append(str(simple_path))

            # 保存内嵌图片（清洗文件名：仅取纯文件名，去路径遍历）
            for name, img_b64 in lr.get("markdown", {}).get("images", {}).items():
                safe_name = Path(name).name  # 去除路径部分，仅保留文件名
                if not safe_name:
                    continue
                img_path = page_dir / safe_name
                img_path.write_bytes(base64.b64decode(img_b64))

            logger.info(f"  Saved: {page_dir} ({len(md_text)} chars)")

        return markdown_files