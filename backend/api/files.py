"""
FastAPI 文件管理路由模块

实现文件上传/下载/预览 API：
- POST /upload - 上传文件
- GET /{id} - 下载文件
- GET /{id}/preview - 预览文件
- GET /{id}/versions - 获取版本列表
- GET /share/{token}/{id} - 公开分享访问
- GET /share/{token}/{id}/preview - 公开分享预览

保留完整安全检查：
- 路径遍历防护
- 双重扩展名检查
- MIME 类型验证
- 文件大小限制
"""
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi import UploadFile as FastUploadFile, File as FastFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from models import File, Conversation
from api.deps import get_current_user, get_db, audit_log
from services.file_storage import FileStorage
from services.document_processor import DocumentProcessor
from config import Config
from utils.error_handler import safe_error_response

logger = logging.getLogger(__name__)

# 创建文件管理路由
router = APIRouter(prefix="/api/files", tags=["files"])

# 常量配置
MAX_PREVIEW_SIZE = 10 * 1024 * 1024  # 10MB - 预览文件大小限制
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB - 上传文件大小限制
ALLOWED_EXTENSIONS = {
    '.txt', '.md',  # 文档类型
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'
}

BINARY_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'
}

# MIME 类型白名单
ALLOWED_MIME_TYPES = {
    'text/plain', 'text/markdown', 'text/x-markdown',
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation'
}

# 危险扩展名黑名单（用于检测双重扩展名攻击）
DANGEROUS_EXTENSIONS = {
    '.php', '.php3', '.php4', '.php5', '.phtml', '.phar',
    '.exe', '.bat', '.cmd', '.com', '.scr',
    '.sh', '.bash', '.zsh',
    '.py', '.pyw',
    '.pl', '.cgi',
    '.jsp', '.asp', '.aspx',
    '.html', '.htm', '.xhtml'
}


def is_safe_path(file_path: str) -> bool:
    """
    验证文件路径是否在允许的上传目录内

    使用 Path.relative_to() 进行严格验证，防止：
    1. 路径遍历攻击 (../)
    2. 符号链接绕过
    3. 路径伪造
    """
    try:
        base_dir = Config.FILE_STORAGE_PATH or 'data/files'
        base_path = Path(base_dir).resolve()
        file_path_obj = Path(file_path).resolve()
        file_path_obj.relative_to(base_path)
        return file_path_obj != base_path
    except ValueError:
        return False
    except Exception as e:
        logger.warning(f"Path validation failed: {str(e)}")
        return False


def check_file_access(file_id: int, user_id: int, db_session: Session):
    """检查文件访问权限,返回(file_record, error_response)"""
    file_record = db_session.get(File, file_id)
    if not file_record:
        return None, HTTPException(status_code=404, detail={'error': '文件不存在'})

    if file_record.user_id != user_id:
        return None, HTTPException(status_code=403, detail={'error': '无权访问此文件'})

    if file_record.conversation_id:
        conversation = db_session.get(Conversation, file_record.conversation_id)
        if not conversation:
            return None, HTTPException(status_code=404, detail={'error': '对话不存在'})
        if conversation.user_id != user_id:
            return None, HTTPException(status_code=403, detail={'error': '无权访问此文件'})

    return file_record, None


def allowed_file(filename: str, file_content: bytes = None) -> tuple[bool, str | None]:
    """
    检查文件扩展名是否允许

    增强验证：
    1. 扩展名白名单检查
    2. 双重扩展名攻击防护
    3. MIME 类型验证（如果提供文件内容）
    """
    if '.' not in filename:
        return False, '文件缺少扩展名'

    ext = '.' + filename.rsplit('.', 1)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        return False, f'不支持的文件类型: {ext}'

    # 双重扩展名检查
    parts = filename.lower().split('.')
    if len(parts) > 2:
        for i in range(1, len(parts) - 1):
            middle_ext = '.' + parts[i]
            if middle_ext in DANGEROUS_EXTENSIONS:
                return False, f'检测到危险的双重扩展名: {middle_ext}'

    # MIME 类型验证
    if file_content:
        try:
            import magic
            mime_type = magic.from_buffer(file_content, mime=True)

            if mime_type not in ALLOWED_MIME_TYPES and mime_type != 'application/octet-stream':
                logger.warning(
                    f"MIME type mismatch: file={filename}, "
                    f"declared_ext={ext}, actual_mime={mime_type}"
                )
                return False, f'文件内容类型不匹配: {mime_type}'
        except ImportError:
            logger.warning("python-magic not installed, skipping MIME validation")
        except Exception as e:
            logger.error(f"MIME type check failed: {str(e)}")

    return True, None


def is_binary_file(filename: str) -> bool:
    """判断文件是否为二进制文件"""
    if '.' not in filename:
        return False
    ext = '.' + filename.rsplit('.', 1)[-1].lower()
    return ext in BINARY_EXTENSIONS


def get_temp_directory() -> str:
    """获取临时文件目录名"""
    return 'temp'


@router.post("/upload")
async def upload_file(
    file: FastUploadFile = FastFile(...),
    conversation_id: int = Form(default=None),
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """上传文件"""
    try:
        # 验证对话权限
        if conversation_id:
            conversation = db_session.get(Conversation, conversation_id)
            if not conversation:
                raise HTTPException(status_code=404, detail={'success': False, 'error': '对话不存在'})
            if conversation.user_id != user.id:
                raise HTTPException(status_code=403, detail={'success': False, 'error': '无权访问此对话'})

        # 提取扩展名（在 secure_filename 之前）
        original_ext = None
        if file.filename and '.' in file.filename:
            original_ext = '.' + file.filename.rsplit('.', 1)[1].lower()

        if not original_ext:
            raise HTTPException(
                status_code=400,
                detail={'success': False, 'error': '文件缺少扩展名'}
            )

        # 扩展名白名单检查
        if original_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail={'success': False, 'error': f'不支持的文件类型。允许的类型: {", ".join(ALLOWED_EXTENSIONS)}'}
            )

        # 前置检查文件大小（避免大文件读入内存）
        if file.size and file.size > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail={'success': False, 'error': f'文件过大。最大允许 {MAX_UPLOAD_SIZE // (1024 * 1024)}MB'}
            )

        # 流式分块读取：累计大小超限立即中止，防止超大请求整体载入内存（OOM）
        _CHUNK_SIZE = 1024 * 1024  # 1MB
        _chunks = []
        file_size = 0
        while True:
            chunk = await file.read(_CHUNK_SIZE)
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail={'success': False, 'error': f'文件过大。最大允许 {MAX_UPLOAD_SIZE // (1024 * 1024)}MB'}
                )
            _chunks.append(chunk)
        file_content = b''.join(_chunks)

        # 安全处理文件名
        from werkzeug.utils import secure_filename
        safe_filename_str = secure_filename(file.filename or '')

        if not safe_filename_str or '.' not in safe_filename_str:
            safe_filename_str = f"file_{uuid.uuid4().hex[:8]}{original_ext}"

        original_filename = safe_filename_str
        storage_conversation_id = str(conversation_id) if conversation_id else get_temp_directory()

        # 使用 FileStorage 保存文件
        file_storage = FileStorage(Config.FILE_STORAGE_PATH or 'data/files')

        if original_ext in BINARY_EXTENSIONS:
            # 增强验证：双重扩展名和 MIME 类型检查
            is_allowed, error_msg = allowed_file(file.filename or '', file_content=file_content)
            if not is_allowed:
                raise HTTPException(status_code=400, detail={'success': False, 'error': error_msg})

            file_metadata = file_storage.save_file_binary(
                conversation_id=storage_conversation_id,
                message_id='0',
                filename=original_filename,
                content=file_content
            )
        else:
            try:
                text_content = file_content.decode('utf-8')
                is_allowed, error_msg = allowed_file(file.filename or '')
                if not is_allowed:
                    raise HTTPException(status_code=400, detail={'success': False, 'error': error_msg})

                file_metadata = file_storage.save_file(
                    conversation_id=storage_conversation_id,
                    message_id='0',
                    filename=original_filename,
                    content=text_content
                )
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail={'success': False, 'error': '无法读取文件内容,请确保文件为文本格式'})

        # 创建文件记录
        file_record = File(
            conversation_id=conversation_id,
            message_id=None,
            user_id=user.id,
            filename=file_metadata['filename'],
            file_path=file_metadata['file_path'],
            file_type=file_metadata['file_type'],
            file_size=file_metadata['file_size'],
            version=file_metadata['version']
        )
        db_session.add(file_record)
        db_session.commit()

        logger.info(f"文件上传成功: {original_filename} (ID: {file_record.id})")

        # 审计日志
        audit_log(user.id, 'file.upload', 'file', file_record.id,
                  {'filename': file_record.filename, 'size': file_record.file_size}, db_session)
        db_session.commit()

        return {
            'success': True,
            'file_id': file_record.id,
            'filename': file_record.filename,
            'file_size': file_record.file_size,
            'file_type': file_record.file_type
        }

    except HTTPException:
        raise
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail={'success': False, 'error': '无法读取文件内容,请确保文件为文本格式'})
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=safe_error_response(e, '保存文件失败'))


@router.get("/")
async def list_files(
    conversation_id: int,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """获取指定对话的文件列表"""
    try:
        # 验证对话权限
        conversation = db_session.get(Conversation, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail={'error': '对话不存在'})
        if conversation.user_id != user.id:
            raise HTTPException(status_code=403, detail={'error': '无权访问此对话'})

        files = db_session.query(File).filter_by(
            conversation_id=conversation_id,
            user_id=user.id
        ).order_by(File.created_at.desc()).all()

        return [f.to_dict() for f in files]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文件列表错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail={'error': '获取文件列表失败'})


@router.get("/{file_id}/download")
async def download_file_alias(
    file_id: int,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """下载文件（/download 别名，兼容前端调用）"""
    return await download_file(file_id, user, db_session)


@router.get("/{file_id}")
async def download_file(
    file_id: int,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """下载文件"""
    try:
        file_record, error = check_file_access(file_id, user.id, db_session)
        if error:
            raise error

        if not is_safe_path(file_record.file_path):
            logger.warning(f"Path traversal attempt: {file_record.file_path}")
            raise HTTPException(status_code=403, detail={'error': '非法文件路径'})

        if not os.path.exists(file_record.file_path):
            raise HTTPException(status_code=404, detail={'error': '文件不存在于磁盘'})

        # 审计日志
        audit_log(user.id, 'file.download', 'file', file_id,
                  {'filename': file_record.filename}, db_session)
        db_session.commit()

        return FileResponse(
            file_record.file_path,
            filename=file_record.filename,
            media_type=file_record.file_type
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载文件错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail={'error': '下载文件失败'})


def _preview_file_impl(file_record: File) -> dict:
    """
    预览文件的核心实现（提取自 preview_file / preview_file_by_share_token）。

    前置条件：调用方已验证权限、路径安全、文件存在、大小上限。

    Args:
        file_record: 已验证的 File ORM 对象

    Returns:
        预览结果 dict

    Raises:
        HTTPException: 文件读取或解码失败
    """
    filename = file_record.filename

    # 检查是否为需要解析的文档类型
    if DocumentProcessor.is_supported(filename):
        result = DocumentProcessor.process_document_from_path(filename, file_record.file_path)

        if result['success']:
            return {
                'filename': filename,
                'file_type': file_record.file_type,
                'content': result['text'],
                'is_binary': True,
                'is_document': True,
                'metadata': result.get('metadata', {})
            }
        else:
            return {
                'filename': filename,
                'file_type': file_record.file_type,
                'content': f'[文档解析失败: {result.get("error", "未知错误")}]',
                'is_binary': True,
                'is_document': True,
                'parse_error': result.get('error')
            }

    if is_binary_file(filename):
        return {
            'filename': filename,
            'file_type': file_record.file_type,
            'content': '[二进制文件，不支持文本预览]',
            'is_binary': True
        }

    with open(file_record.file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    return {
        'filename': filename,
        'file_type': file_record.file_type,
        'content': content,
        'is_binary': False
    }


@router.get("/{file_id}/preview")
async def preview_file(
    file_id: int,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """预览文件"""
    try:
        file_record, error = check_file_access(file_id, user.id, db_session)
        if error:
            raise error

        if not is_safe_path(file_record.file_path):
            raise HTTPException(status_code=403, detail={'error': '非法文件路径'})

        if not os.path.exists(file_record.file_path):
            raise HTTPException(status_code=404, detail={'error': '文件不存在于磁盘'})

        # 【FIX-P1】预览大小改用实测磁盘大小（避免 DB file_size 伪造/NULL 绕过）
        actual_size = os.path.getsize(file_record.file_path)
        if actual_size > MAX_PREVIEW_SIZE:
            raise HTTPException(status_code=400, detail={'error': '文件过大，无法预览'})

        return _preview_file_impl(file_record)

    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail={'error': '无法预览此类型的文件'})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预览文件错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail={'error': '预览文件失败'})


@router.get("/{file_id}/versions")
async def get_file_versions(
    file_id: int,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """获取文件的所有版本"""
    try:
        file_record, error = check_file_access(file_id, user.id, db_session)
        if error:
            raise error

        versions = db_session.query(File).filter_by(
            conversation_id=file_record.conversation_id,
            filename=file_record.filename
        ).order_by(File.version).all()

        return [v.to_dict() for v in versions]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文件版本错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail={'error': '获取文件版本失败'})


# 公开分享端点（无需认证）
@router.get("/share/{share_token}/{file_id}/preview")
async def preview_file_by_share_token(
    share_token: str,
    file_id: int,
    db_session: Session = Depends(get_db)
):
    """通过分享令牌公开预览文件（无需认证）"""
    try:
        conversation = db_session.query(Conversation).filter_by(share_token=share_token).first()
        if not conversation:
            raise HTTPException(status_code=404, detail={'error': '对话不存在或链接已失效'})

        file_record = db_session.get(File, file_id)
        if not file_record:
            raise HTTPException(status_code=404, detail={'error': '文件不存在'})

        if file_record.conversation_id != conversation.id:
            raise HTTPException(status_code=403, detail={'error': '无权访问此文件'})

        if not is_safe_path(file_record.file_path):
            raise HTTPException(status_code=403, detail={'error': '非法文件路径'})

        if not os.path.exists(file_record.file_path):
            raise HTTPException(status_code=404, detail={'error': '文件不存在于磁盘'})

        # 【FIX-P0】公开分享端点补大小上限（实测磁盘真实大小，避免 DB 字段伪造/NULL 绕过）
        actual_size = os.path.getsize(file_record.file_path)
        if actual_size > MAX_PREVIEW_SIZE:
            raise HTTPException(status_code=400, detail={'error': '文件过大，不支持预览（上限 10MB）'})

        return _preview_file_impl(file_record)

    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail={'error': '无法预览此类型的文件'})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"公开预览文件错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail={'error': '预览文件失败'})


@router.get("/share/{share_token}/{file_id}")
async def download_file_by_share_token(
    share_token: str,
    file_id: int,
    db_session: Session = Depends(get_db)
):
    """通过分享令牌公开下载文件（无需认证）"""
    try:
        conversation = db_session.query(Conversation).filter_by(share_token=share_token).first()
        if not conversation:
            raise HTTPException(status_code=404, detail={'error': '对话不存在或链接已失效'})

        file_record = db_session.get(File, file_id)
        if not file_record:
            raise HTTPException(status_code=404, detail={'error': '文件不存在'})

        if file_record.conversation_id != conversation.id:
            raise HTTPException(status_code=403, detail={'error': '无权访问此文件'})

        if not is_safe_path(file_record.file_path):
            raise HTTPException(status_code=403, detail={'error': '非法文件路径'})

        if not os.path.exists(file_record.file_path):
            raise HTTPException(status_code=404, detail={'error': '文件不存在于磁盘'})

        return FileResponse(
            file_record.file_path,
            filename=file_record.filename,
            media_type=file_record.file_type
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"公开下载文件错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail={'error': '下载文件失败'})