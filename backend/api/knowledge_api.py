"""
FastAPI Knowledge API 路由模块

实现知识库管理 API：
- GET /documents - 获取文档列表
- GET /categories - 获取分类列表
- GET /documents/{id}/download - 下载文档
- GET /status - 获取知识库状态
- GET /graph - 获取知识图谱路径
- POST /upload - 上传文档
- DELETE /documents/{id} - 删除文档
- POST /refresh-index - 刷新索引
- GET /admin/categories - 获取分类列表（个人 + 共享）
- POST /admin/categories - 创建分类
- PUT /admin/categories/{id} - 更新分类
- DELETE /admin/categories/{id} - 删除分类

保留后台 OCR 任务（ThreadPoolExecutor）。
"""
import functools
import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db, get_admin_user, resolve_request_locale
from models import KnowledgeDocument, KnowledgeCategory, User
from config import Config
from services.catalog_localization_service import catalog_localization_service
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

# 创建 Knowledge 路由
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# 常量配置（默认分类，仅作回退；实际校验走数据库）
DEFAULT_CATEGORIES = {'default', 'regulation', 'workflow', 'contract', 'news'}

# 后台任务执行器（全局单例）
_background_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='knowledge-ocr')


# ==================== Pydantic 模型 ====================

class CategoryCreateRequest(BaseModel):
    key: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    description: Optional[str] = None
    icon: Optional[str] = "Document"
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True


class CategoryUpdateRequest(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# ==================== 辅助函数 ====================

def trigger_background_processing(doc_id: int):
    """后台触发 OCR + graphify 处理

    注意：不复用调用方的 db_session（请求结束后即关闭），
    后台线程内自行创建独立 session。
    """
    def process_task():
        from db import get_db_session
        from services.ocr_processor import OcrProcessor
        from services.graphify_extractor import GraphifyExtractor

        bg_db = get_db_session()
        try:
            doc = bg_db.get(KnowledgeDocument, doc_id)
            if not doc:
                logger.warning(f'Document {doc_id} not found for background processing')
                return

            logger.info(f'Starting background processing for doc {doc_id}: {doc.filename}')

            # Step 1: OCR 处理
            ocr_processor = OcrProcessor(db_session=bg_db)
            ocr_result = ocr_processor.process_knowledge_document(doc_id)

            if ocr_result['success']:
                # 刷新 ORM 状态（process_knowledge_document 已 commit）
                bg_db.refresh(doc)

                # Step 2: graphify 提取
                graphify_extractor = GraphifyExtractor(db_session=bg_db)
                graphify_result = graphify_extractor.extract_document(doc_id)
                logger.info(f'Graphify extraction completed for doc {doc_id}: nodes={graphify_result.get("nodes", 0)}')
            else:
                logger.warning(f'OCR processing failed for doc {doc_id}: {ocr_result.get("error", "unknown")}')

            logger.info(f'Background processing completed for doc {doc_id}')
        except Exception:
            logger.exception(f'Background processing failed for doc {doc_id}')
        finally:
            bg_db.close()

    _background_executor.submit(process_task)


def get_knowledge_storage_path() -> Path:
    """获取知识库存储根目录（统一使用 Config.KNOWLEDGE_DATA_DIR）"""
    knowledge_path = Path(Config.KNOWLEDGE_DATA_DIR)
    knowledge_path.mkdir(parents=True, exist_ok=True)
    return knowledge_path


def get_document_storage_path(doc_id: int) -> Path:
    """获取文档存储目录"""
    knowledge_path = get_knowledge_storage_path()
    doc_path = knowledge_path / 'documents' / str(doc_id) / 'original'
    doc_path.mkdir(parents=True, exist_ok=True)
    return doc_path


def _is_system_knowledge_category(category: KnowledgeCategory) -> bool:
    """Shared categories are product-owned; personal categories stay source-owned."""
    return category.user_id is None


def _localize_knowledge_category(
    category: KnowledgeCategory,
    locale,
    *,
    include_count: int | None = None,
) -> dict:
    data = category.to_dict()
    source_label = category.label
    data['name'] = source_label
    localized = catalog_localization_service.localize_item(
        data=data,
        entity_type='knowledge_category',
        key=category.key,
        source_name=source_label,
        is_system=_is_system_knowledge_category(category),
        locale=locale,
    )
    if include_count is not None:
        localized['count'] = include_count
    return localized


# ==================== 公开端点 ====================

@router.get("/documents")
async def list_documents(
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db),
    category: Optional[str] = Query(default=None)
):
    """获取文档列表（支持分类过滤）"""
    try:
        query = db_session.query(KnowledgeDocument).filter(KnowledgeDocument.uploaded_by == user.id)

        if category:
            # 动态校验：查数据库中的活跃分类（个人 + 共享）
            valid_keys = {c.key for c in db_session.query(KnowledgeCategory).filter(
            or_(
                KnowledgeCategory.user_id == user.id,
                KnowledgeCategory.user_id.is_(None)
            ),
            KnowledgeCategory.is_active == True
        ).all()}
            valid_keys.add('default')
            if not valid_keys:
                valid_keys = DEFAULT_CATEGORIES
            if category not in valid_keys:
                raise HTTPException(
                    status_code=400,
                    detail={
                        'error': 'Invalid category',
                        'message': f'category must be one of: {", ".join(sorted(valid_keys))}'
                    }
                )
            query = query.filter_by(category=category)

        documents = query.all()

        return {
            'documents': [doc.to_dict() for doc in documents],
            'total': len(documents)
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception('Failed to list documents')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to list documents', 'message': 'An internal error occurred'}
        )


@router.get("/categories")
async def list_categories(
    request: Request,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db),
    locale: Optional[str] = Query(default=None)
):
    """获取分类列表"""
    try:
        from sqlalchemy import func, or_
        request_locale = resolve_request_locale(request, locale, user)

        categories = db_session.query(KnowledgeCategory).filter(
            or_(
                KnowledgeCategory.user_id == user.id,
                KnowledgeCategory.user_id.is_(None)
            ),
            KnowledgeCategory.is_active == True
        ).order_by('sort_order').all()

        # 统计每个分类的文档数（仅统计当前用户的文档）
        doc_counts = {}
        count_result = db_session.query(
            KnowledgeDocument.category,
            func.count(KnowledgeDocument.id).label('count')
        ).filter(KnowledgeDocument.uploaded_by == user.id).group_by(KnowledgeDocument.category).all()

        for row in count_result:
            doc_counts[row.category] = row.count

        total_docs = db_session.query(KnowledgeDocument).filter(KnowledgeDocument.uploaded_by == user.id).count()

        category_list = []
        for cat in categories:
            category_list.append(_localize_knowledge_category(
                cat,
                request_locale,
                include_count=doc_counts.get(cat.key, 0),
            ))

        return {
            'categories': category_list,
            'total_docs': total_docs
        }

    except Exception:
        logger.exception('Failed to list categories')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to list categories', 'message': 'An internal error occurred'}
        )


@router.get("/documents/{doc_id}/preview")
async def preview_document(
    doc_id: int,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """预览文档内容

    优先返回 OCR 生成的 Markdown 内容；无则用 DocumentProcessor 解析原文件。
    """
    try:
        doc = db_session.get(KnowledgeDocument, doc_id)
        if not doc:
            raise HTTPException(
                status_code=404,
                detail={'error': 'Document not found', 'message': f'Document {doc_id} does not exist'}
            )

        # 归属检查
        if doc.uploaded_by != user.id:
            raise HTTPException(
                status_code=403,
                detail={'error': 'Forbidden', 'message': '无权访问此文档'}
            )

        MAX_PREVIEW_SIZE = 10 * 1024 * 1024  # 10MB

        # 优先使用 OCR 生成的 Markdown（markdown_path 可能是目录或文件）
        if doc.markdown_path and os.path.exists(doc.markdown_path):
            if os.path.isdir(doc.markdown_path):
                # 目录结构：markdown_path/page_XXXX/doc.md → 按页拼接
                page_dirs = sorted(
                    p for p in Path(doc.markdown_path).iterdir()
                    if p.is_dir() and p.name.startswith('page_')
                )
                parts = []
                total_size = 0
                for page_dir in page_dirs:
                    md_file = page_dir / 'doc.md'
                    if md_file.exists():
                        text = md_file.read_text(encoding='utf-8')
                        total_size += len(text.encode('utf-8'))
                        if total_size > MAX_PREVIEW_SIZE:
                            parts.append('\n\n---\n\n[预览截断：内容过长]')
                            break
                        parts.append(text)
                content = '\n\n---\n\n'.join(parts) if parts else '[文档暂无内容]'
            else:
                # 兼容旧格式：直接指向文件
                if os.path.getsize(doc.markdown_path) > MAX_PREVIEW_SIZE:
                    raise HTTPException(status_code=400, detail={'error': '文件过大，无法预览'})
                content = Path(doc.markdown_path).read_text(encoding='utf-8')
            return {
                'filename': doc.filename,
                'file_type': 'md',
                'content': content,
                'is_document': True
            }

        # 无 OCR 结果：根据文档状态给出明确提示
        if doc.status in ('pending', 'processing'):
            return {
                'filename': doc.filename,
                'file_type': doc.file_type,
                'content': '[文档正在处理中（OCR 索引），请稍后刷新预览]',
                'is_document': True,
                'ocr_status': doc.status
            }

        # 退回原文件解析（OCR 已完成但无 markdown，或非 PDF 文件）
        if not doc.original_path or not os.path.exists(doc.original_path):
            raise HTTPException(
                status_code=404,
                detail={'error': 'File not found', 'message': '文档文件不存在'}
            )

        if doc.file_size and doc.file_size > MAX_PREVIEW_SIZE:
            raise HTTPException(status_code=400, detail={'error': '文件过大，无法预览'})

        from services.document_processor import DocumentProcessor

        if DocumentProcessor.is_supported(doc.filename):
            result = DocumentProcessor.process_document_from_path(doc.filename, doc.original_path)
            if result['success']:
                # 扫描版 PDF 提示：追加 OCR 状态信息
                content = result['text']
                if result.get('warning') and doc.status == 'failed':
                    content += f'\n\n> OCR 处理失败：{doc.ocr_error or "未知原因"}'
                return {
                    'filename': doc.filename,
                    'file_type': doc.file_type,
                    'content': content,
                    'is_document': True,
                    'metadata': result.get('metadata', {}),
                    'ocr_status': doc.status
                }
            return {
                'filename': doc.filename,
                'file_type': doc.file_type,
                'content': f'[文档解析失败: {result.get("error", "未知错误")}]',
                'is_document': True,
                'parse_error': result.get('error')
            }

        # 文本文件直接返回（全量读入，先检查大小防 OOM）
        if doc.file_size and doc.file_size > MAX_PREVIEW_SIZE:
            raise HTTPException(status_code=400, detail={'error': '文件过大，无法预览'})
        try:
            file_content = Path(doc.original_path).read_bytes()
            content = file_content.decode('utf-8')
            return {
                'filename': doc.filename,
                'file_type': doc.file_type,
                'content': content,
                'is_document': False
            }
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail={'error': f'文件不存在: {doc.filename}'})
        except UnicodeDecodeError:
            # 图片文件：返回文件类型标记，前端可据此渲染
            IMAGE_TYPES = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
            if doc.file_type.lower() in IMAGE_TYPES:
                if doc.file_size and doc.file_size > MAX_PREVIEW_SIZE:
                    raise HTTPException(status_code=400, detail={'error': '文件过大，无法预览'})
                import base64
                b64_data = base64.b64encode(file_content).decode()
                mime = f"image/{'jpeg' if doc.file_type.lower() in ('jpg', 'jpeg') else doc.file_type.lower()}"
                return {
                    'filename': doc.filename,
                    'file_type': doc.file_type,
                    'content': f'![{doc.original_filename or doc.filename}](data:{mime};base64,{b64_data})',
                    'is_document': True,
                    'is_image': True,
                    'ocr_status': doc.status
                }
            return {
                'filename': doc.filename,
                'file_type': doc.file_type,
                'content': '[二进制文件，不支持文本预览]',
                'is_binary': True
            }

    except HTTPException:
        raise
    except Exception:
        logger.exception(f'Failed to preview document: {doc_id}')
        raise HTTPException(
            status_code=500,
            detail={'error': '预览文档失败', 'message': 'An internal error occurred'}
        )


@router.get("/documents/{doc_id}/download")
async def download_document(
    doc_id: int,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """下载文档"""
    try:
        doc = db_session.get(KnowledgeDocument, doc_id)
        if not doc:
            raise HTTPException(
                status_code=404,
                detail={'error': 'Document not found', 'message': f'Document {doc_id} does not exist'}
            )

        # 归属检查
        if doc.uploaded_by != user.id:
            raise HTTPException(
                status_code=403,
                detail={'error': 'Forbidden', 'message': '无权访问此文档'}
            )

        if not doc.original_path or not os.path.exists(doc.original_path):
            raise HTTPException(
                status_code=404,
                detail={'error': 'File not found', 'message': 'Document file does not exist on disk'}
            )

        return FileResponse(
            doc.original_path,
            filename=doc.filename,
            media_type=f'application/{doc.file_type}'
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception(f'Failed to download document: {doc_id}')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to download document', 'message': 'An internal error occurred'}
        )


@router.get("/status")
async def get_status(
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """获取知识库状态统计"""
    try:
        total_docs = db_session.query(KnowledgeDocument).filter(KnowledgeDocument.uploaded_by == user.id).count()
        indexed_docs = db_session.query(KnowledgeDocument).filter(
            KnowledgeDocument.uploaded_by == user.id,
            KnowledgeDocument.status == 'indexed'
        ).count()
        pending_docs = db_session.query(KnowledgeDocument).filter(
            KnowledgeDocument.uploaded_by == user.id,
            KnowledgeDocument.status == 'pending'
        ).count()

        # 从用户图谱 JSON 读取图谱统计
        graph_stats = {'nodes': 0, 'edges': 0, 'communities': 0}
        graph_json_path = Config.get_user_graph_path(user.id)
        if graph_json_path and os.path.exists(graph_json_path):
            try:
                import json
                data = json.loads(Path(graph_json_path).read_text(encoding='utf-8'))
                graph_stats['nodes'] = len(data.get('nodes', []))
                graph_stats['edges'] = len(data.get('links', data.get('edges', [])))
                communities = set()
                for node in data.get('nodes', []):
                    cid = node.get('community')
                    if cid is not None:
                        communities.add(cid)
                graph_stats['communities'] = len(communities)
            except Exception:
                logger.warning(f'Failed to read user {user.id} graph.json for stats')

        return {
            'total_docs': total_docs,
            'indexed_docs': indexed_docs,
            'pending_docs': pending_docs,
            'graph_stats': graph_stats
        }

    except Exception:
        logger.exception('Failed to get knowledge status')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to get knowledge status', 'message': 'An internal error occurred'}
        )


@router.get("/graph-data")
async def get_graph_data(
    community: Optional[str] = Query(default=None, description="按 community ID 过滤"),
    limit: int = Query(default=1000, ge=1, description="返回节点数上限"),
    user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取知识图谱完整数据（供前端 D3 渲染）

    支持 community 过滤和 limit 截断。
    返回 graph.json 数据 + community 汇总 + source_file → KnowledgeDocument 映射。
    """
    import json
    from collections import defaultdict

    graph_json_path = Config.get_user_graph_path(user.id)
    if not graph_json_path or not os.path.exists(graph_json_path):
        # 图谱尚未生成，返回空结构（前端已处理 null 场景）
        return {
            'nodes': [],
            'links': [],
            'communities': [],
            'total_nodes': 0,
            'total_links': 0,
        }

    try:
        data = json.loads(Path(graph_json_path).read_text(encoding='utf-8'))
    except Exception:
        logger.exception('Failed to read graph.json')
        raise HTTPException(status_code=500, detail={'error': 'Failed to read graph data'})

    nodes = data.get('nodes', [])
    links = data.get('links', data.get('edges', []))

    # 记录全量计数
    total_nodes = len(nodes)
    total_links = len(links)

    # community 过滤
    if community is not None:
        nodes = [n for n in nodes if str(n.get('community')) == community]
        node_id_set = {n.get('id') for n in nodes}
        links = [
            lk for lk in links
            if lk.get('source') in node_id_set and lk.get('target') in node_id_set
        ]

    # limit 截断
    nodes = nodes[:limit]

    # 截断后只保留两端节点都在截断结果中的 link
    node_id_set = {n.get('id') for n in nodes}
    links = [
        lk for lk in links
        if lk.get('source') in node_id_set and lk.get('target') in node_id_set
    ]

    # Community 汇总：{id, count, sample_labels}
    community_map = defaultdict(lambda: {'count': 0, 'labels': []})
    for node in nodes:
        cid = node.get('community')
        if cid is None:
            continue
        community_map[cid]['count'] += 1
        if len(community_map[cid]['labels']) < 3:
            community_map[cid]['labels'].append(node.get('label', ''))
    communities = [
        {'id': cid, 'count': info['count'], 'sample_labels': info['labels']}
        for cid, info in sorted(community_map.items())
    ]

    # doc_map：source_file 前缀（page_xxx）→ KnowledgeDocument 信息
    # source_file 格式：page_0001/doc.md，markdown_path 指向包含 page_xxx/ 的目录
    source_prefixes = set()
    for node in nodes:
        sf = node.get('source_file')
        if sf and '/' in sf:
            source_prefixes.add(sf.split('/')[0])

    doc_map = {}
    if source_prefixes:
        # 过滤当前用户的文档
        indexed_docs = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.uploaded_by == user.id,
            KnowledgeDocument.status == 'indexed',
            KnowledgeDocument.markdown_path.isnot(None)
        ).all()
        for doc in indexed_docs:
            if not doc.markdown_path or not os.path.isdir(doc.markdown_path):
                continue
            for prefix in source_prefixes:
                if prefix in doc_map:
                    continue
                candidate = Path(doc.markdown_path) / prefix
                if candidate.is_dir():
                    doc_map[prefix] = {
                        'doc_id': doc.id,
                        'filename': doc.original_filename or doc.filename,
                        'status': doc.status
                    }

    return {
        'nodes': nodes,
        'links': links,
        'communities': communities,
        'doc_map': doc_map,
        'total_nodes': total_nodes,
        'total_links': total_links,
    }


@router.get("/gap-analysis")
async def get_gap_analysis(user = Depends(get_current_user)):
    """知识图谱缺口分析

    分析图谱结构，识别知识薄弱区域和跨领域缺口。
    """
    import json
    from services.gap_analysis_service import GapAnalysisService

    graph_json_path = Config.get_user_graph_path(user.id)
    if not graph_json_path or not os.path.exists(graph_json_path):
        # 图谱尚未生成，返回空缺口分析结果
        return {
            'gaps': [],
            'summary': '知识图谱尚未生成，请上传文档后刷新索引',
            'total_gaps': 0,
        }

    try:
        data = json.loads(Path(graph_json_path).read_text(encoding='utf-8'))
    except Exception:
        logger.exception('Failed to read graph.json')
        raise HTTPException(status_code=500, detail={'error': 'Failed to read graph data'})

    analyzer = GapAnalysisService()
    return analyzer.analyze(data)


@router.post("/upload")
async def upload_document(
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db),
    file: UploadFile = File(...),
    category: str = Form(...),
    allow_duplicate: str = Form(default='false')
):
    """上传文档"""
    try:
        from utils.upload_validator import validate_upload

        user_id = user.id

        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail={'error': 'Bad request', 'message': 'No file selected'}
            )

        # 动态校验分类：查数据库中的活跃分类（个人 + 共享）
        valid_keys = {c.key for c in db_session.query(KnowledgeCategory).filter(
            or_(
                KnowledgeCategory.user_id == user.id,
                KnowledgeCategory.user_id.is_(None)
            ),
            KnowledgeCategory.is_active == True
        ).all()}
        # 始终包含 'default'（前端硬编码使用，个人分类由 auth 注册或迁移回填）
        valid_keys.add('default')
        if not valid_keys:
            valid_keys = DEFAULT_CATEGORIES
        if category not in valid_keys:
            raise HTTPException(
                status_code=400,
                detail={'error': 'Invalid category', 'message': f'category must be one of: {", ".join(sorted(valid_keys))}'}
            )

        # 读取文件内容
        file_content = await file.read()
        check_duplicate = allow_duplicate.lower() != 'true'

        # 使用 upload_validator 进行完整校验（传入 bytes）
        result = validate_upload(
            file_content,
            file.filename,
            check_duplicate=check_duplicate,
            db_session=db_session
        )

        if not result.valid:
            if result.error_code == 'duplicate':
                raise HTTPException(
                    status_code=409,
                    detail={
                        'error': 'Duplicate file',
                        'error_code': 'duplicate',
                        'message': f'文件内容与文档 ID {result.duplicate_doc_id} 相同',
                        'duplicate_doc_id': result.duplicate_doc_id,
                        'content_hash': result.content_hash
                    }
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail={'error': result.error, 'error_code': result.error_code}
                )

        # 安全处理文件名
        original_name = file.filename  # 保留用户原始文件名
        safe_filename_str = secure_filename(file.filename)

        import uuid
        if not safe_filename_str or '.' not in safe_filename_str:
            safe_filename_str = f"doc_{uuid.uuid4().hex[:8]}{result.file_ext}"

        # 创建数据库记录
        doc = KnowledgeDocument(
            filename=safe_filename_str,
            original_filename=original_name,
            category=category,
            file_size=result.file_size,
            file_type=result.file_ext.lstrip('.'),
            content_hash=result.content_hash,
            uploaded_by=user_id,
            status='pending'
        )
        db_session.add(doc)
        db_session.flush()

        # 保存文件
        doc_path = get_document_storage_path(doc.id)
        file_save_path = doc_path / safe_filename_str

        if result.is_binary:
            with open(file_save_path, 'wb') as f:
                f.write(file_content)
        else:
            try:
                text_content = file_content.decode('utf-8')
                with open(file_save_path, 'w', encoding='utf-8') as f:
                    f.write(text_content)
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail={'error': 'Invalid file content', 'message': 'Text file must be UTF-8 encoded'}
                )

        doc.original_path = str(file_save_path)
        db_session.commit()

        # 触发后台 OCR + graphify 处理
        trigger_background_processing(doc.id)

        logger.info(f'Document uploaded: id={doc.id}, filename={safe_filename_str}, category={category}')

        response = doc.to_dict()
        response['message'] = '文档上传成功，正在后台处理索引...'
        return response

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception('Failed to upload document')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to upload document', 'message': 'An internal error occurred'}
        )


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: int,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """删除文档"""
    try:
        doc = db_session.get(KnowledgeDocument, doc_id)
        if not doc:
            raise HTTPException(
                status_code=404,
                detail={'error': 'Document not found', 'message': f'Document {doc_id} does not exist'}
            )

        # 归属检查
        if doc.uploaded_by != user.id:
            raise HTTPException(
                status_code=403,
                detail={'error': 'Forbidden', 'message': '无权删除此文档'}
            )

        # 记录用户 ID（删除后需重建该用户图谱）
        user_id = doc.uploaded_by

        # 删除文件目录（路径安全校验：确保在存储根目录内）
        if doc.original_path:
            doc_dir = Path(doc.original_path).parent.parent
            storage_root = get_knowledge_storage_path().resolve()
            if doc_dir.exists() and doc_dir.resolve().is_relative_to(storage_root):
                shutil.rmtree(doc_dir, ignore_errors=True)
                logger.info(f'Document directory deleted: {doc_dir}')
            else:
                logger.warning(f'Document directory outside storage root, skipping delete: {doc_dir}')

        db_session.delete(doc)
        db_session.commit()

        logger.info(f'Document deleted: id={doc_id}')

        # 重建用户图谱（删除后需更新该用户图谱）
        try:
            from services.graphify_extractor import GraphifyExtractor
            GraphifyExtractor(db_session).rebuild_user_graph(user_id)
            # 清除 GraphRAG 缓存（图谱文件已变更）
            from services.graph_rag_service import GraphRAGService
            GraphRAGService.get_instance().clear_user_cache(user_id)
            logger.info(f'User graph rebuilt after document deletion: user_id={user_id}')
        except Exception as e:
            logger.warning(f'Failed to rebuild user graph after deletion: {e}')

        return None

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to delete document: {doc_id}')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to delete document', 'message': 'An internal error occurred'}
        )


@router.post("/refresh-index")
async def refresh_index(
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """刷新索引——立即返回，后台异步执行"""
    try:
        pending_docs = db_session.query(KnowledgeDocument).filter(
            KnowledgeDocument.uploaded_by == user.id,
            KnowledgeDocument.status == 'pending'
        ).all()
        failed_docs = db_session.query(KnowledgeDocument).filter(
            KnowledgeDocument.uploaded_by == user.id,
            KnowledgeDocument.status == 'failed'
        ).all()
        indexed_no_graph = db_session.query(KnowledgeDocument).filter(
            KnowledgeDocument.uploaded_by == user.id,
            KnowledgeDocument.status == 'indexed',
            (KnowledgeDocument.graph_nodes.is_(None)) | (KnowledgeDocument.graph_nodes == 0)
        ).all()

        all_doc_ids = [doc.id for doc in pending_docs + failed_docs + indexed_no_graph]
        total = len(all_doc_ids)

        if total == 0:
            # 无文档需重新处理，但仍翻译已有图谱标签
            _background_executor.submit(_translate_user_graph_task, user.id)
            return {'message': '无需刷新的文档，正在翻译图谱标签', 'total': 0}

        # 后台异步执行
        _background_executor.submit(_refresh_index_task, all_doc_ids)

        logger.info(f'Refresh index dispatched: {total} documents queued')
        return {'message': '刷新已启动', 'total': total}

    except Exception:
        logger.exception('Failed to dispatch refresh index')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to refresh index', 'message': 'An internal error occurred'}
        )


def _translate_user_graph_task(user_id: int):
    """后台翻译用户图谱节点标签为中文"""
    try:
        from services.graphify_extractor import GraphifyExtractor
        from config import Config

        graph_path = Config.get_user_graph_path(user_id)
        if graph_path and os.path.exists(graph_path):
            extractor = GraphifyExtractor()
            extractor._translate_graph_labels(graph_path)
            logger.info(f'User graph labels translated: user_id={user_id}')
    except Exception:
        logger.exception(f'Failed to translate user graph labels: user_id={user_id}')


def _refresh_index_task(doc_ids: list[int]):
    """后台刷新索引任务：独立 session，逐文档 OCR + graphify"""
    from db import get_db_session
    from services.ocr_processor import OcrProcessor
    from services.graphify_extractor import GraphifyExtractor

    bg_db = get_db_session()
    try:
        ocr_processor = OcrProcessor(db_session=bg_db)
        graphify_extractor = GraphifyExtractor(db_session=bg_db)

        ocr_success = 0
        extract_success = 0

        for doc_id in doc_ids:
            doc = bg_db.get(KnowledgeDocument, doc_id)
            if not doc:
                continue

            # OCR 处理（pending / failed 文档）
            if doc.status in ('pending', 'failed'):
                result = ocr_processor.process_knowledge_document(doc_id)
                if result.get('success'):
                    ocr_success += 1
                    bg_db.refresh(doc)  # 刷新 ORM 状态（OCR 已 commit）
                else:
                    logger.warning(f'OCR failed for doc {doc_id}: {result.get("error")}')

            # graphify 提取（indexed 且无 graph_nodes 的文档，或刚 OCR 成功的文档）
            if doc and doc.status == 'indexed' and (not doc.graph_nodes or doc.graph_nodes == 0):
                result = graphify_extractor.extract_document(doc_id)
                if result.get('success'):
                    extract_success += 1
                else:
                    logger.warning(f'Graphify failed for doc {doc_id}: {result.get("error")}')

        # 按用户分组重建图谱（替代全局合并）
        processed_user_ids = set()
        for doc_id in doc_ids:
            doc = bg_db.get(KnowledgeDocument, doc_id)
            if doc and doc.uploaded_by:
                processed_user_ids.add(doc.uploaded_by)
        for uid in processed_user_ids:
            graphify_extractor._merge_user_graph(uid)

        logger.info(f'Refresh index completed: OCR {ocr_success} success, graphify {extract_success} success')
    except Exception:
        logger.exception('Background refresh index failed')
    finally:
        bg_db.close()


# ==================== Admin 分类管理 ====================

@router.get("/admin/categories")
async def admin_list_categories(
    request: Request,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db),
    locale: Optional[str] = Query(default=None)
):
    """获取分类列表（个人 + 共享）"""
    try:
        from sqlalchemy import or_
        request_locale = resolve_request_locale(request, locale, user)

        categories = db_session.query(KnowledgeCategory).filter(
            or_(
                KnowledgeCategory.user_id == user.id,
                KnowledgeCategory.user_id.is_(None)
            )
        ).order_by('sort_order').all()
        return {
            'categories': [
                _localize_knowledge_category(cat, request_locale)
                for cat in categories
            ]
        }

    except Exception:
        logger.exception('Failed to list admin categories')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to list categories', 'message': 'An internal error occurred'}
        )


@router.post("/admin/categories", status_code=201)
async def admin_create_category(
    request: CategoryCreateRequest,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """创建新分类"""
    try:
        key = request.key.strip()
        label = request.label.strip()

        if not key:
            raise HTTPException(status_code=400, detail={'error': 'Bad request', 'message': 'key is required'})
        if not label:
            raise HTTPException(status_code=400, detail={'error': 'Bad request', 'message': 'label is required'})

        # 检查 key 是否已存在（仅校验当前用户 + 共享分类，不跨用户）
        existing = db_session.query(KnowledgeCategory).filter(
            KnowledgeCategory.key == key,
            or_(
                KnowledgeCategory.user_id == user.id,
                KnowledgeCategory.user_id.is_(None)
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail={'error': 'Category key already exists', 'message': f'key "{key}" is already used'}
            )

        category = KnowledgeCategory(
            key=key,
            label=label,
            description=request.description or '',
            icon=request.icon or 'Document',
            sort_order=request.sort_order or 0,
            is_active=request.is_active if request.is_active is not None else True,
            user_id=user.id  # 设置为当前用户的个人分类
        )
        db_session.add(category)
        db_session.commit()

        logger.info(f'Category created: key={key}, label={label}, user_id={user.id}')
        return category.to_dict()

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception('Failed to create category')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to create category', 'message': 'An internal error occurred'}
        )


@router.put("/admin/categories/{category_id}")
async def admin_update_category(
    category_id: int,
    request: CategoryUpdateRequest,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """更新分类"""
    try:
        category = db_session.get(KnowledgeCategory, category_id)
        if not category:
            raise HTTPException(
                status_code=404,
                detail={'error': 'Category not found', 'message': f'Category {category_id} does not exist'}
            )

        # 权限检查：仅允许修改自己的分类，共享分类（user_id IS NULL）不可修改
        if category.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail={'error': 'Forbidden', 'message': '无权修改此分类'}
            )

        if request.label is not None:
            category.label = request.label
        if request.description is not None:
            category.description = request.description
        if request.icon is not None:
            category.icon = request.icon
        if request.sort_order is not None:
            category.sort_order = request.sort_order
        if request.is_active is not None:
            category.is_active = request.is_active

        db_session.commit()

        logger.info(f'Category updated: id={category_id}, key={category.key}, user_id={user.id}')
        return category.to_dict()

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to update category: {category_id}')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to update category', 'message': 'An internal error occurred'}
        )


@router.delete("/admin/categories/{category_id}", status_code=204)
async def admin_delete_category(
    category_id: int,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """删除分类"""
    try:
        category = db_session.get(KnowledgeCategory, category_id)
        if not category:
            raise HTTPException(
                status_code=404,
                detail={'error': 'Category not found', 'message': f'Category {category_id} does not exist'}
            )

        # 权限检查：仅允许删除自己的分类，共享分类（user_id IS NULL）不可删除
        if category.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail={'error': 'Forbidden', 'message': '无权删除此分类'}
            )

        category_key = category.key

        # 将该分类下的文档归入默认分类（default="未分类"，避免 category NOT NULL 冲突）
        # 个人分类仅归当前用户的文档；共享分类（user_id IS NULL）归全量
        doc_query = db_session.query(KnowledgeDocument).filter(
            KnowledgeDocument.category == category_key
        )
        if category.user_id is not None:
            doc_query = doc_query.filter(KnowledgeDocument.uploaded_by == user.id)
        doc_query.update({'category': 'default'})

        db_session.delete(category)
        db_session.commit()

        logger.info(f'Category deleted: id={category_id}, key={category_key}, user_id={user.id}')
        return None

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to delete category: {category_id}')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to delete category', 'message': 'An internal error occurred'}
        )
