"""Backend services module.

业务服务层，封装可被多个 API 调用的业务逻辑。
"""

# OCR 处理器（原有）
from .ocr_processor import OcrProcessor

# 核心服务
from .llm_service import LLMService
from .file_storage import FileStorage
from .document_processor import DocumentProcessor

# Agent 相关
from .agent_file_manager import AgentFileManager
from .agent_metadata import AgentMetadataParser

# 工具/技能管理
from .tools_registry import get_tools_registry
from .skills_manager import get_skills_manager

__all__ = [
    'OcrProcessor',
    'LLMService',
    'FileStorage',
    'DocumentProcessor',
    'AgentFileManager',
    'AgentMetadataParser',
    'get_tools_registry',
    'get_skills_manager',
]
