"""
FastAPI 应用入口

应用入口，实现：
- lifespan 管理（目录创建 + MCP 异步初始化/关闭）
- CORS middleware
- slowapi rate limiter
"""
import logging
import logging.handlers
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

# 加载环境变量（必须在 config 导入前）
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from config import config
from db import db, Base, engine, SessionLocal
from utils.rate_limit import limiter


class TimezoneFormatter(logging.Formatter):
    """以明确的部署时区格式化日志时间戳。"""

    def __init__(self, *args, timezone_name: str = 'Asia/Shanghai', **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.timezone = ZoneInfo(timezone_name)
            self.timezone_name = timezone_name
        except (ZoneInfoNotFoundError, ValueError):
            # 即使镜像既没有系统 zoneinfo 也没有 Python tzdata 包，
            # 也要保证启动流程与日志格式化仍可工作。
            self.timezone = timezone(timedelta(hours=8), name='Asia/Shanghai')
            self.timezone_name = 'Asia/Shanghai'

    def formatTime(self, record, datefmt=None):
        current = datetime.fromtimestamp(record.created, self.timezone)
        return current.strftime(datefmt) if datefmt else current.isoformat(timespec='milliseconds')


class JSONFormatter(TimezoneFormatter):
    """JSON 结构化日志格式化器，通过 STRUCTURED_LOGGING=true 启用"""
    def format(self, record):
        log_entry = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def _configure_logging():
    """配置应用日志"""
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, 'backend.log')
    log_level = logging.DEBUG if os.environ.get('APP_ENV') == 'development' else logging.INFO

    # 根据环境变量选择格式化器
    use_json = os.environ.get('STRUCTURED_LOGGING', '').lower() == 'true'
    timezone_name = os.environ.get('LOG_TIMEZONE', 'Asia/Shanghai').strip() or 'Asia/Shanghai'
    formatter = JSONFormatter(
        datefmt='%Y-%m-%d %H:%M:%S',
        timezone_name=timezone_name,
    ) if use_json else TimezoneFormatter(
        '%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        timezone_name=timezone_name,
    )

    # 文件处理器
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.info('Logging configured: %s (timezone=%s)', log_file, formatter.timezone_name)


# Rate limiter 实例（从 rate_limit 模块导入）


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Rate limit exceeded 异常处理器"""
    if exc.detail == 'RATE_LIMITED':
        return JSONResponse(
            status_code=429,
            content={
                'detail': {
                    'code': 'RATE_LIMITED',
                    'error': '请求过于频繁，请稍后重试',
                }
            },
        )
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"}
    )


def _http_exception_handler(request: Request, exc: HTTPException):
    """
    HTTPException 异常处理器

    统一 401 错误格式为 {error: "...", message: "..."}，
    兼容旧版响应格式，前端无需改动。
    """
    # 处理 401 认证错误
    if exc.status_code == 401:
        # detail 可能是 dict 或 str
        if isinstance(exc.detail, dict):
            # 已经是 {error, message} 格式
            return JSONResponse(
                status_code=401,
                content=exc.detail
            )
        elif isinstance(exc.detail, str):
            # 转换为统一格式
            return JSONResponse(
                status_code=401,
                content={"error": exc.detail, "message": exc.detail}
            )
        else:
            return JSONResponse(
                status_code=401,
                content={"error": "认证失败", "message": str(exc.detail)}
            )

    # 其他 HTTP 错误，保持 FastAPI 默认格式
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理

    Startup:
    1. 配置日志
    2. 创建必要目录
    3. MCP 异步初始化

    Shutdown:
    1. MCP 连接关闭
    """
    # 启动
    _configure_logging()
    logging.info("FastAPI application starting up")

    # 创建必要目录
    basedir = os.path.abspath(os.path.dirname(__file__))
    os.makedirs(os.path.join(basedir, 'data', 'files'), exist_ok=True)
    os.makedirs(os.path.join(basedir, 'data', 'workspace'), exist_ok=True)
    os.makedirs(os.path.join(basedir, 'logs'), exist_ok=True)
    logging.info("Required directories created")

    # MCP 异步初始化（测试环境跳过）
    if os.environ.get('SKIP_MCP_INIT') != 'true':
        try:
            from services.mcp.mcp_manager import init_mcp_async, shutdown_mcp
            await init_mcp_async()
            logging.info("MCP manager initialized successfully")
        except Exception as e:
            logging.warning(f"MCP manager init failed: {e}")

    # 验证 Agent 配置（DB 优先，回退到文件系统）
    from config import Config
    try:
        from models import AgentConfig as _AgentConfig
        _session = SessionLocal()
        try:
            db_agent_count = _session.query(_AgentConfig).filter(_AgentConfig.is_enabled == True).count()
        finally:
            _session.close()
        if db_agent_count > 0:
            logging.info(f"Agents loaded from DB: {db_agent_count} agents")
        else:
            raise RuntimeError("DB has no agents, fallback to file system")
    except Exception:
        agents_dir = Config.AGENTS_DIR
        if agents_dir and os.path.isdir(agents_dir):
            agent_count = len([f for f in os.listdir(agents_dir) if f.endswith('.md')])
            logging.info(f"Agents directory: {agents_dir} ({agent_count} agents)")
        else:
            logging.warning(f"Agents directory not found: {agents_dir} — "
                            "Agent features will be unavailable. "
                            "Check AGENTS_DIR env or volume mount.")

    try:
        from services.agentteams_integration_launch import (
            find_recoverable_agentteams_launch_ids,
            schedule_agentteams_launch,
            start_agentteams_recovery_monitor,
        )
        recoverable_launch_ids = find_recoverable_agentteams_launch_ids()
        for launch_id in recoverable_launch_ids:
            schedule_agentteams_launch(launch_id)
        start_agentteams_recovery_monitor()
        if recoverable_launch_ids:
            logging.info(
                "Scheduled %s recoverable Agent Teams launches",
                len(recoverable_launch_ids),
            )
    except Exception:
        logging.warning("Agent Teams launch recovery scan failed", exc_info=True)

    try:
        from translation.cache import find_recoverable_translation_ids
        from translation.tasks import (
            schedule_translation,
            start_translation_recovery_monitor,
        )
        recoverable_translation_ids = find_recoverable_translation_ids()
        for translation_id in recoverable_translation_ids:
            schedule_translation(translation_id)
        start_translation_recovery_monitor()
        if recoverable_translation_ids:
            logging.info(
                'Scheduled %s recoverable content translations',
                len(recoverable_translation_ids),
            )
    except Exception:
        logging.warning('Translation recovery scan failed', exc_info=True)

    yield

    # 关闭
    logging.info("FastAPI application shutting down")
    try:
        from services.agentteams_integration_launch import shutdown_agentteams_launch_tasks
        await shutdown_agentteams_launch_tasks()
    except Exception:
        logging.warning("Agent Teams launch task shutdown failed", exc_info=True)
    try:
        from translation.tasks import shutdown_translation_tasks
        await shutdown_translation_tasks()
    except Exception:
        logging.warning('Translation task shutdown failed', exc_info=True)
    try:
        from services.mcp.mcp_manager import shutdown_mcp
        await shutdown_mcp()
        logging.info("MCP shutdown complete")
    except Exception as e:
        logging.warning(f"MCP shutdown failed: {e}")


# 创建 FastAPI 应用实例
config_name = os.environ.get('APP_ENV', 'default')
app_config = config[config_name]

# 生产环境关闭交互式 API 文档，避免暴露接口结构
# fail-closed：除 development 外的一切环境（含未设置）均按生产处理
_is_production = os.environ.get('APP_ENV') != 'development'

app = FastAPI(
    title="Agent Teams API",
    description="团队导向的 Agent Teams Web API，支持 SSE 实时对话、Agent 团队协作、Leader 智能协调等功能。",
    version=app_config.APP_VERSION,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    lifespan=lifespan,
)

# 注册 CORS middleware（从配置读取允许的来源）
cors_origins = [
    origin.strip()
    for origin in (app_config.CORS_ORIGINS or 'http://localhost:5173').split(',')
    if origin.strip()
]

# 凭证模式下拒绝通配符来源：浏览器会直接拒绝该组合，
# 等效于对所有站点开放带凭证跨域，必须在启动时暴露配置错误
if '*' in cors_origins:
    raise ValueError(
        "CORS_ORIGINS 不允许使用 '*'（当前 allow_credentials=True）。\n"
        "请在 .env 中配置具体的前端来源，例如：\n"
        "CORS_ORIGINS=http://localhost:5173,https://yourdomain.com"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 rate limiter middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(HTTPException, _http_exception_handler)
app.add_middleware(SlowAPIMiddleware)

# 注册路由
from api.health_api import router as health_router
from api.auth import router as auth_router
from api.locales import router as locales_router
from api.conversations import router as conversations_router
from api.files import router as files_router
from api.agents_api import router as agents_router
from api.tools_api import router as tools_router
from api.skills_api import router as skills_router
from api.mcp_api import router as mcp_router
from api.knowledge_api import router as knowledge_router
from api.admin_api import router as admin_router
from api.project_config_api import router as project_config_router
from api.admin_roles_api import router as admin_roles_router
from api.leader_api import router as leader_router
from api.llm_models_api import router as llm_models_router
from api.agent_api import router as user_agent_router
from api.agent_pack_api import router as agent_pack_router
from api.workflow_template_api import router as workflow_template_router
from api.agentteams_integration_api import (
    router as agentteams_integration_router,
    generic_router as integration_gateway_router,
)
from api.content_translation_api import router as content_translation_router
from api.decision_run_api import (
    legacy_router as decision_evidence_legacy_router,
    router as decision_run_router,
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(locales_router)
app.include_router(conversations_router)
app.include_router(files_router)
app.include_router(agents_router)
app.include_router(tools_router)
app.include_router(skills_router)
app.include_router(mcp_router)
app.include_router(knowledge_router)
app.include_router(admin_router)
app.include_router(project_config_router)
app.include_router(admin_roles_router)
app.include_router(leader_router)
app.include_router(llm_models_router)
app.include_router(user_agent_router)
app.include_router(agent_pack_router)
app.include_router(workflow_template_router)
app.include_router(agentteams_integration_router)
app.include_router(integration_gateway_router)
app.include_router(content_translation_router)
app.include_router(decision_run_router)
app.include_router(decision_evidence_legacy_router)

_api_prefix_count = sum(1 for r in app.routes if hasattr(r, 'path') and r.path.startswith('/api/'))
logging.info(f"FastAPI app instance created with {_api_prefix_count} API routes registered")


# ==================== 测试兼容层 ====================

def create_app(config_name: str = None):
    """
    创建应用实例（测试兼容层）

    测试需使用 TestClient。
    此函数为兼容 pytest fixture 而保留。

    Args:
        config_name: 配置名称（testing/development/production）

    Returns:
        FastAPI app 实例
    """
    # 如果传入 config_name，设置环境变量
    if config_name:
        os.environ['APP_ENV'] = config_name

    # 返回全局 app 实例（FastAPI 单例模式）
    return app
