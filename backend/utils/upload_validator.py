"""知识库文件上传校验模块

提供完整的上传安全校验：
- 扩展名白名单检查
- 双重扩展名攻击防护
- 文件大小限制
- 内容哈希计算（用于去重）
- 重复文件检测

兼容 FastAPI UploadFile（接受 bytes 内容）。
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Optional


logger = logging.getLogger(__name__)


# === 常量配置 ===

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB - 上传文件大小限制

# 白名单：覆盖 graphify 支持格式（排除视频）
KNOWLEDGE_ALLOWED_EXTENSIONS = {
    # CODE - graphify 支持的代码文件
    '.py', '.pyw', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.ejs', '.ets',
    '.go', '.rs', '.java', '.groovy', '.gradle',
    '.cpp', '.cc', '.cxx', '.c', '.h', '.hpp',
    '.rb', '.swift', '.kt', '.kts', '.cs', '.scala', '.php',
    '.lua', '.luau', '.vue', '.svelte', '.astro', '.dart',
    '.sql', '.sh', '.bash', '.json', '.yaml', '.yml',
    # DOC - 文档类型
    '.md', '.mdx', '.qmd', '.txt', '.rst', '.html',
    # PAPER - PDF
    '.pdf',
    # IMAGE - 图片（graphify 支持 vision 提取）
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg',
    # OFFICE - Office 文档
    '.docx', '.xlsx', '.doc', '.xls', '.ppt', '.pptx',
}

# 二进制文件类型（用于区分保存方式）
KNOWLEDGE_BINARY_EXTENSIONS = {
    '.pdf', '.docx', '.xlsx', '.doc', '.xls', '.ppt', '.pptx',
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg',
}

# MIME 白名单：合并 graphify 相关类型
KNOWLEDGE_ALLOWED_MIME_TYPES = {
    # 文本
    'text/plain', 'text/markdown', 'text/x-markdown', 'text/html',
    # PDF
    'application/pdf',
    # Office - Word
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    # Office - Excel
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    # Office - PowerPoint
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    # 图片
    'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/svg+xml',
}

# 危险扩展名黑名单（用于双重扩展名攻击防护）
DANGEROUS_EXTENSIONS = {
    '.php', '.php3', '.php4', '.php5', '.phtml', '.phar',
    '.exe', '.bat', '.cmd', '.com', '.scr',
    '.sh', '.bash', '.zsh',
    '.py', '.pyw',
    '.pl', '.cgi',
    '.jsp', '.asp', '.aspx',
    '.html', '.htm', '.xhtml',
}


@dataclass
class ValidationResult:
    """校验结果数据结构"""
    valid: bool
    error: Optional[str] = None
    error_code: Optional[str] = None  # 'invalid_extension' | 'too_large' | 'dangerous_double_ext' | 'mime_mismatch' | 'duplicate'
    file_ext: str = ''
    file_size: int = 0
    content_hash: Optional[str] = None  # MD5 哈希，用于去重检测
    is_binary: bool = False
    duplicate_doc_id: Optional[int] = None  # 如果存在重复，返回已存在文档 ID


def validate_upload(
    file_content: bytes,        # 文件二进制内容
    filename: str,              # 原始文件名
    check_duplicate: bool = True,  # 是否检查重复
    db_session = None,          # 用于查询已存在文档
    user_id: Optional[int] = None  # 查重范围限定为该用户（知识库按用户隔离）
) -> ValidationResult:
    """
    完整校验流程：
    1. 扩展名白名单检查
    2. 双重扩展名攻击防护
    3. 文件大小检查
    4. MIME 类型验证
    5. 内容哈希计算（用于去重）
    6. 重复检测（可选）

    Args:
        file_content: 文件二进制内容（bytes）
        filename: 原始文件名
        check_duplicate: 是否检查重复文件
        db_session: SQLAlchemy session，用于查询已存在文档
        user_id: 传入时查重仅匹配该用户的文档，避免向其他用户的存在性预言机泄露

    Returns:
        ValidationResult: 校验结果
    """
    # 1. 扩展名白名单检查
    if '.' not in filename:
        return ValidationResult(
            valid=False,
            error='文件缺少扩展名',
            error_code='invalid_extension'
        )

    ext = '.' + filename.rsplit('.', 1)[1].lower()

    if ext not in KNOWLEDGE_ALLOWED_EXTENSIONS:
        allowed_list = ', '.join(sorted(KNOWLEDGE_ALLOWED_EXTENSIONS))
        return ValidationResult(
            valid=False,
            error=f'不支持的文件类型: {ext}。支持的类型: {allowed_list}',
            error_code='invalid_extension',
            file_ext=ext
        )

    # 2. 双重扩展名攻击防护
    # 例如: file.php.txt, file.exe.pdf
    parts = filename.lower().split('.')
    if len(parts) > 2:
        # 检查所有中间扩展名是否为危险类型
        for i in range(1, len(parts) - 1):
            middle_ext = '.' + parts[i]
            if middle_ext in DANGEROUS_EXTENSIONS:
                return ValidationResult(
                    valid=False,
                    error=f'检测到危险的双重扩展名: {middle_ext}',
                    error_code='dangerous_double_ext',
                    file_ext=ext
                )

    # 3. 文件大小检查
    file_size = len(file_content)

    if file_size > MAX_UPLOAD_SIZE:
        return ValidationResult(
            valid=False,
            error=f'文件大小超出限制 ({MAX_UPLOAD_SIZE // (1024*1024)}MB)',
            error_code='too_large',
            file_ext=ext,
            file_size=file_size
        )

    # 4. MIME 类型验证（读取文件头）
    mime_valid, mime_error = _validate_mime_type(file_content, ext)
    if not mime_valid:
        return ValidationResult(
            valid=False,
            error=mime_error,
            error_code='mime_mismatch',
            file_ext=ext,
            file_size=file_size
        )

    # 5. 内容哈希计算
    content_hash = compute_content_hash(file_content)

    # 判断是否为二进制文件
    is_binary = ext in KNOWLEDGE_BINARY_EXTENSIONS

    # 6. 重复检测（可选）
    if check_duplicate and db_session:
        duplicate_doc_id = check_duplicate_by_hash(content_hash, db_session, user_id=user_id)
        if duplicate_doc_id:
            return ValidationResult(
                valid=False,
                error=f'文件内容与文档 ID {duplicate_doc_id} 相同',
                error_code='duplicate',
                file_ext=ext,
                file_size=file_size,
                content_hash=content_hash,
                is_binary=is_binary,
                duplicate_doc_id=duplicate_doc_id
            )

    # 校验通过
    return ValidationResult(
        valid=True,
        file_ext=ext,
        file_size=file_size,
        content_hash=content_hash,
        is_binary=is_binary
    )


def compute_content_hash(file_content: bytes) -> str:
    """
    计算文件内容 MD5 哈希

    Args:
        file_content: 文件二进制内容

    Returns:
        str: MD5 哈希（32 字符）
    """
    return hashlib.md5(file_content, usedforsecurity=False).hexdigest()


def _validate_mime_type(file_content: bytes, expected_ext: str) -> tuple[bool, Optional[str]]:
    """
    验证文件 MIME 类型

    Args:
        file_content: 文件二进制内容
        expected_ext: 预期的扩展名

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        import magic

        header = file_content[:256]
        mime_type = magic.from_buffer(header, mime=True)

        if mime_type not in KNOWLEDGE_ALLOWED_MIME_TYPES and mime_type != 'application/octet-stream':
            logger.warning(
                f"MIME type mismatch: file_ext={expected_ext}, actual_mime={mime_type}"
            )
            return False, f'文件内容类型不匹配: {mime_type}'

        return True, None

    except ImportError:
        logger.warning("python-magic not installed, skipping MIME validation")
        return True, None

    except Exception as e:
        logger.error(f"MIME type check failed: {str(e)}")
        return True, None


def check_duplicate_by_hash(content_hash: str, db_session, user_id: Optional[int] = None) -> Optional[int]:
    """
    检查是否有相同哈希的已存在文档

    Args:
        content_hash: MD5 哈希
        db_session: SQLAlchemy session
        user_id: 传入时仅匹配该用户上传的文档（知识库按用户隔离，
                 跨用户命中不应作为 409 泄露其他用户文档的存在与 ID）

    Returns:
        Optional[int]: 已存在文档 ID，无重复返回 None
    """
    from models import KnowledgeDocument

    query = db_session.query(KnowledgeDocument).filter(
        KnowledgeDocument.content_hash == content_hash
    )
    if user_id is not None:
        query = query.filter(KnowledgeDocument.uploaded_by == user_id)

    existing_doc = query.first()

    if existing_doc:
        return existing_doc.id

    return None