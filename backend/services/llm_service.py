"""
LLM 服务模块
使用 OpenAI 兼容 API 的服务模块，支持流式输出
适配豆包（火山引擎）等国产大模型
"""
import asyncio
import os
import time
import json
import re
import threading
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import List, Dict, Generator, Optional, Callable, Any, Tuple, Type, TypeVar
from openai import OpenAI, RateLimitError
from pydantic import BaseModel

try:
    import instructor
except ImportError:  # pragma: no cover - 运行时由 fallback 处理
    class _MissingInstructor:
        def patch(self, *_args, **_kwargs):
            raise RuntimeError("instructor is not installed")

        def from_openai(self, *_args, **_kwargs):
            raise RuntimeError("instructor is not installed")

    instructor = _MissingInstructor()

T = TypeVar("T", bound=BaseModel)

_ACTIVE_USAGE_CAPTURE: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "llm_usage_capture",
    default=None,
)

# 配置日志
logger = logging.getLogger(__name__)


class ContextWindowExceededError(RuntimeError):
    """当前请求无法在不丢弃最新用户提示词的情况下放入上下文窗口。"""

    error_code = "context_window_exceeded"

# 配置常量（默认值，实际运行时以 DB llm_models.max_output_tokens 为准）
MAX_TOKENS_EXTENDED = 65536  # call_sync/call_stream 签名兜底默认值（所有调用方均显式传参覆盖）
DEFAULT_MODEL = "ep-default"  # 仅用于显式构造 LLMService 的内部兼容默认值

# 重试配置
RETRY_MAX_ATTEMPTS = 5       # 最大重试次数（降低避免长时间阻塞 worker）
RETRY_INTERVAL = 10          # 重试间隔（秒）

# 全局并发信号量：限制同一时刻并行的 LLM API 调用
# 多个 Agent / 子任务并发（默认 MAX_AGENT_PARALLEL=5）会瞬时打爆账号的 tpm 配额，
# 用进程级信号量收敛并发度。可通过环境变量 LLM_MAX_CONCURRENT_CALLS 调整。
# 注意语义：进程内全局、跨模型/账号共享；流式调用在整个响应消费期持锁。
# Docker 部署以 --workers 4 运行时全实例上限为 4 × 本值（见 docs/deployment/docker-deploy.md）。
LLM_MAX_CONCURRENT_CALLS = max(1, int(os.environ.get('LLM_MAX_CONCURRENT_CALLS', '3')))
_LLM_CALL_SEMAPHORE = threading.Semaphore(LLM_MAX_CONCURRENT_CALLS)

# 429 限流退避：即使调用方传 max_attempts 较小（如子任务分析 max_attempts=1，
# 意图是"其它错误快速失败"），限流也应独立获得额外重试预算，避免分析因配额耗尽而全失败。
RATE_LIMIT_MAX_EXTRA_RETRIES = 3
RATE_LIMIT_BACKOFF_BASE = 5.0
# Retry-After 与指数退避共用同一封顶：异常网关返回的大值
# （如 3600s）不得长期占住全局并发槽位冻结工作流线程。
RATE_LIMIT_RETRY_AFTER_CAP_SECONDS = 60.0


def _is_rate_limit_error(error: Exception) -> bool:
    """判断是否 429 限流错误（openai.RateLimitError 或任意 status_code/response 429）。"""
    if isinstance(error, RateLimitError):
        return True
    if getattr(error, 'status_code', None) == 429:
        return True
    resp = getattr(error, 'response', None)
    if resp is not None and getattr(resp, 'status_code', None) == 429:
        return True
    return False


def _retry_after_from_error(error: Exception) -> Optional[float]:
    """从限流错误的 Retry-After 响应头提取等待秒数；不存在则返回 None。"""
    resp = getattr(error, 'response', None)
    if resp is not None:
        headers = getattr(resp, 'headers', None)
        if headers and headers.get('Retry-After'):
            try:
                return float(headers['Retry-After'])
            except (TypeError, ValueError):
                return None
    return None


def _rate_limit_backoff(error: Exception, retry_count: int) -> float:
    """429 退避：优先尊重服务端 Retry-After（封顶），否则指数退避并封顶 60s。"""
    retry_after = _retry_after_from_error(error)
    if retry_after and retry_after > 0:
        return min(retry_after, RATE_LIMIT_RETRY_AFTER_CAP_SECONDS)
    return min(RATE_LIMIT_BACKOFF_BASE * (2 ** (retry_count - 1)), RATE_LIMIT_RETRY_AFTER_CAP_SECONDS)

# 模型规格配置缓存（从 DB 加载，管理端变更时清除）
_MODEL_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def _load_model_config() -> Dict[str, Any]:
    """从数据库加载模型完整配置，结果缓存到进程生命周期。

    管理端增删改模型时调用 invalidate_model_cache() 清除缓存。
    """
    global _MODEL_CONFIG_CACHE
    if _MODEL_CONFIG_CACHE is not None:
        return _MODEL_CONFIG_CACHE

    try:
        from db import db
        from models import LLMModel

        rows = (
            db.query(LLMModel)
            .filter(LLMModel.is_enabled == True)
            .order_by(LLMModel.is_default.desc(), LLMModel.sort_order, LLMModel.id)
            .all()
        )
        _MODEL_CONFIG_CACHE = {
            "defaults": {"context_limit": 128000, "max_output_tokens": 32768},
            "models": {
                m.model_id: {
                    "model_id": m.model_id,
                    "base_url": m.base_url,
                    "api_key": "***MASKED***",
                    "_api_key_ref": m.id,  # 仅存 DB 主键，运行时按需查询明文
                    "context_limit": m.context_limit,
                    "max_output_tokens": m.max_output_tokens,
                }
                for m in rows
            },
            # 小写索引，供 _resolve_model_spec 精确匹配
            "_lower_index": {m.model_id.lower(): m.model_id for m in rows},
            "default_model": rows[0].model_id if rows else None,
        }
        logger.info("Loaded %d model specs from DB", len(_MODEL_CONFIG_CACHE["models"]))
        return _MODEL_CONFIG_CACHE
    except Exception:
        # 失败结果不缓存：缓存空映射会让一次瞬时 DB 故障把该 worker 的模型
        # 解析降级到进程退出（无 TTL，管理端 invalidate 也只影响单个 worker）。
        # 保持 None，下次调用重新尝试加载。
        logger.exception("Failed to load model config from DB")
        _MODEL_CONFIG_CACHE = None
        return {
            "defaults": {"context_limit": 128000, "max_output_tokens": 32768},
            "models": {},
            "_lower_index": {},
            "default_model": None,
        }


def _model_to_runtime_info(model) -> Dict[str, Any]:
    return {
        "id": model.id,
        "model_id": model.model_id,
        "base_url": model.base_url,
        "api_key": model.api_key,
        "context_limit": model.context_limit,
        "max_output_tokens": model.max_output_tokens,
    }


def get_model_info_from_db(model_id: str, db_session=None) -> Optional[Dict[str, Any]]:
    """从缓存获取模型信息，api_key 运行时从 DB 读取明文。

    缓存中 api_key 已脱敏（安全考虑），运行时调用方需要明文时通过此函数获取。
    大小写不敏感精确匹配，无缓存命中时 fallback 到 DB 查询。
    """
    if db_session is not None:
        from models import LLMModel

        model = (
            db_session.query(LLMModel)
            .filter(
                LLMModel.model_id == model_id,
                LLMModel.is_enabled == True,
            )
            .first()
        )
        return _model_to_runtime_info(model) if model else None

    cfg = _load_model_config()
    # 大小写不敏感精确匹配
    lower_index = cfg.get("_lower_index", {})
    real_key = lower_index.get((model_id or "").lower())
    if real_key and real_key in cfg["models"]:
        spec = cfg["models"][real_key]
        # 运行时从 DB 获取明文 api_key
        api_key = _fetch_api_key_from_db(spec.get("_api_key_ref"))
        return {**spec, "api_key": api_key}
    # DB fallback（缓存可能过期）
    try:
        from db import db
        from models import LLMModel

        model = (
            db.query(LLMModel)
            .filter(
                LLMModel.model_id == model_id,
                LLMModel.is_enabled == True,
            )
            .first()
        )
        if not model:
            return None
        return _model_to_runtime_info(model)
    except Exception:
        logger.exception("Failed to query model '%s' from DB", model_id)
        return None


def get_default_model_info_from_db(db_session=None) -> Optional[Dict[str, Any]]:
    """返回启用的数据库默认模型，或第一个已启用的模型。"""
    try:
        from db import db
        from models import LLMModel

        session = db_session if db_session is not None else db
        model = (
            session.query(LLMModel)
            .filter(LLMModel.is_enabled == True)
            .order_by(LLMModel.is_default.desc(), LLMModel.sort_order, LLMModel.id)
            .first()
        )
        return _model_to_runtime_info(model) if model else None
    except Exception:
        logger.exception("Failed to query the default LLM model from DB")
        return None


def get_default_model_id() -> Optional[str]:
    return _load_model_config().get("default_model")


class LLMConfigurationError(RuntimeError):
    """当不存在可用的基于数据库的 LLM 配置时抛出。"""


def resolve_model_info(model_id: Optional[str] = None, db_session=None) -> Dict[str, Any]:
    """解析显式指定的模型或数据库默认模型，不进行环境变量回退。"""
    model_info = (
        get_model_info_from_db(model_id, db_session=db_session)
        if model_id
        else get_default_model_info_from_db(db_session=db_session)
    )
    if model_info:
        return model_info
    if model_id:
        raise LLMConfigurationError(
            f"LLM model '{model_id}' is not configured in the admin database"
        )
    raise LLMConfigurationError(
        "No enabled LLM model is configured in the admin database"
    )


_API_KEY_CACHE_TTL = 60  # API Key 缓存 TTL（秒）
_API_KEY_CACHE_MAX_SIZE = 64  # 缓存条目上限
_api_key_cache: Dict[int, Tuple[float, str]] = {}  # model_id -> (expire_ts, api_key)
_api_key_cache_lock = threading.Lock()


def _fetch_api_key_from_db(model_id_ref: Optional[int]) -> str:
    """从缓存或 DB 获取模型明文 api_key（TTL 60s，避免每次请求查库）"""
    if not model_id_ref:
        return ""
    now = time.monotonic()
    with _api_key_cache_lock:
        cached = _api_key_cache.get(model_id_ref)
        if cached and cached[0] > now:
            return cached[1]
    try:
        from db import db
        from models import LLMModel

        model = db.get(LLMModel, model_id_ref)
        if model:
            with _api_key_cache_lock:
                if len(_api_key_cache) >= _API_KEY_CACHE_MAX_SIZE:
                    oldest_key = min(_api_key_cache, key=lambda k: _api_key_cache[k][0])
                    del _api_key_cache[oldest_key]
                _api_key_cache[model_id_ref] = (now + _API_KEY_CACHE_TTL, model.api_key)
            return model.api_key
    except Exception:
        logger.exception("Failed to fetch api_key from DB for model_id=%s", model_id_ref)
    return ""


def clear_api_key_cache(model_id: Optional[int] = None) -> None:
    """清除 API Key 缓存（管理后台更新密钥后调用）

    Args:
        model_id: 指定模型 ID 清除单条，None 清除全部
    """
    with _api_key_cache_lock:
        if model_id is not None:
            _api_key_cache.pop(model_id, None)
        else:
            _api_key_cache.clear()


def _resolve_model_spec(model_name: str) -> Tuple[int, int]:
    """查找模型规格，返回 (context_limit, max_output_tokens)。

    精确匹配优先（大小写不敏感），无精确匹配时子串 fallback。
    """
    cfg = _load_model_config()
    model_lower = (model_name or "").lower()

    # 精确匹配（通过小写索引）
    lower_index = cfg.get("_lower_index", {})
    if model_lower in lower_index:
        real_key = lower_index[model_lower]
        spec = cfg["models"][real_key]
        return spec["context_limit"], spec["max_output_tokens"]

    # 子串 fallback
    for key, spec in cfg["models"].items():
        if key in model_lower:
            return spec["context_limit"], spec["max_output_tokens"]

    d = cfg["defaults"]
    return d["context_limit"], d["max_output_tokens"]


def invalidate_model_cache():
    """清除模型配置缓存，管理端增删改模型后调用。"""
    global _MODEL_CONFIG_CACHE
    _MODEL_CONFIG_CACHE = None
    clear_api_key_cache()


def create_llm_service(
    model_id: Optional[str] = None,
    *,
    db_session=None,
    agents_dir: str = "",
    workspace_dir: str = "",
) -> "LLMService":
    """从唯一运行时来源 ``llm_models`` 创建 LLM 服务。"""
    model_info = resolve_model_info(model_id, db_session=db_session)
    return LLMService(
        api_key=model_info["api_key"],
        base_url=model_info["base_url"],
        model=model_info["model_id"],
        agents_dir=agents_dir,
        workspace_dir=workspace_dir,
    )


class LLMService:
    """LLM API 集成服务（OpenAI 兼容）"""

    def __init__(self, api_key: str, agents_dir: str = "", workspace_dir: str = "", base_url: str = None, model: str = None):
        """
        初始化 LLM 服务

        Args:
            api_key: API 密钥
            agents_dir: Agents 目录路径
            workspace_dir: 工作空间目录路径
            base_url: API 基础 URL
            model: 模型名称（豆包为推理接入点 ID）
        """
        if not api_key:
            raise ValueError("API key is required")

        self.api_key = api_key
        self.agents_dir = agents_dir
        self.workspace_dir = workspace_dir
        self.model = model or DEFAULT_MODEL
        
        logger.info(
            "LLMService initialized with model='%s', base_url='%s', api_key_configured=%s",
            self.model,
            base_url,
            bool(api_key),
        )

        # 初始化 OpenAI 客户端
        client_kwargs = {
            "api_key": api_key,
            "timeout": 30.0,  # 30 秒超时，与 MCP 客户端一致，避免慢请求长期阻塞
            "max_retries": 0,  # 由本服务统一控制重试，避免 SDK 内部重试叠加导致 SSE 长时间无响应
        }
        if base_url:
            client_kwargs["base_url"] = base_url

        self._client_kwargs = client_kwargs
        self.client = OpenAI(**client_kwargs)
        self._structured_client = None
        self._structured_client_lock = threading.Lock()

    @contextmanager
    def capture_usage(self):
        """捕获当前 Agent 执行上下文中的 LLM 用量。"""
        metrics = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "call_count": 0,
            "failure_count": 0,
            "elapsed": 0.0,
        }
        token = _ACTIVE_USAGE_CAPTURE.set(metrics)
        try:
            yield metrics
        finally:
            _ACTIVE_USAGE_CAPTURE.reset(token)

    @staticmethod
    def _record_usage(
        input_tokens: int,
        output_tokens: int,
        elapsed: float,
        *,
        failed: bool = False,
    ) -> None:
        metrics = _ACTIVE_USAGE_CAPTURE.get()
        if metrics is None:
            return
        input_tokens = max(0, int(input_tokens or 0))
        output_tokens = max(0, int(output_tokens or 0))
        metrics["input_tokens"] += input_tokens
        metrics["output_tokens"] += output_tokens
        metrics["total_tokens"] += input_tokens + output_tokens
        metrics["call_count"] += 1
        metrics["failure_count"] += int(failed)
        metrics["elapsed"] += max(0.0, float(elapsed or 0.0))

    def _get_structured_client(self):
        """获取独立的 Instructor OpenAI 兼容客户端。"""
        if self._structured_client is None:
            with self._structured_client_lock:
                if self._structured_client is None:
                    raw_client = OpenAI(**self._client_kwargs)
                    # 使用 JSON 模式兼容不支持 tool_choice=object 的模型（如 qwen）
                    try:
                        self._structured_client = instructor.from_openai(
                            raw_client, mode=instructor.Mode.JSON
                        )
                    except (AttributeError, TypeError):
                        # instructor 版本不支持 Mode.JSON 或未安装，使用默认模式
                        self._structured_client = instructor.from_openai(raw_client)
        return self._structured_client

    async def call_structured(
        self,
        messages: List[Dict],
        response_model: Type[T],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        max_retries: int = 3,
        temperature: float = 0.0,
        timeout: Optional[float] = None,
    ) -> T:
        """结构化 LLM 调用，返回 Pydantic 模型实例。"""
        if not isinstance(response_model, type) or not issubclass(response_model, BaseModel):
            raise TypeError("response_model must be a Pydantic BaseModel subclass")

        compressed_messages = self._compress_if_needed(
            messages,
            max_tokens=max_tokens or self.get_max_output_tokens(),
        )
        client = self._get_structured_client()
        token_limit = self.clamp_max_tokens(max_tokens or self.get_max_output_tokens())
        input_text = "".join(str(message.get("content") or "") for message in compressed_messages)
        started_at = time.perf_counter()
        try:
            # 全局并发信号量：结构化调用同样收敛并发度，避免打爆 tpm 配额。
            # 信号量必须在工作线程内获取（asyncio.to_thread），不能在事件循环线程里
            # 同步 acquire——否则 semaphore 满时会把整个事件循环（含 SSE 推送）一起阻塞。
            def _guarded_create():
                with _LLM_CALL_SEMAPHORE:
                    return client.chat.completions.create(
                        model=model or self.model,
                        messages=compressed_messages,
                        response_model=response_model,
                        max_tokens=token_limit,
                        max_retries=max_retries,
                        temperature=temperature,
                        timeout=timeout,
                        # 显式禁用 tool_choice，兼容 DeepSeek thinking 模式和 qwen 等国产模型
                        tool_choice="none",
                    )

            result = await asyncio.to_thread(_guarded_create)
        except Exception:
            self._record_usage(
                self.estimate_tokens(input_text),
                0,
                time.perf_counter() - started_at,
                failed=True,
            )
            raise

        output_text = result.model_dump_json() if isinstance(result, BaseModel) else str(result)
        self._record_usage(
            self.estimate_tokens(input_text),
            self.estimate_tokens(output_text),
            time.perf_counter() - started_at,
        )
        return result

    # 模型规格从 DB llm_models 表加载，管理端变更时清除缓存
    # 保留类属性供 agents_api 等外部模块读取（惰性加载）
    DEFAULT_CONTEXT_LIMIT = 128000
    DEFAULT_MAX_OUTPUT_TOKENS = 32768

    @classmethod
    def get_model_specs(cls) -> Dict[str, Dict[str, int]]:
        """返回所有已注册模型规格 {model_id: {context_limit, max_output_tokens}}。"""
        cfg = _load_model_config()
        return {
            mid: {"context_limit": s["context_limit"], "max_output_tokens": s["max_output_tokens"]}
            for mid, s in cfg["models"].items()
        }

    # 估算安全系数：1 字符 ≈ 0.5 token（中文约 1.5 字符/token，英文约 4 字符/token）
    CHARS_PER_TOKEN = 2.0

    def estimate_tokens(self, text: str) -> int:
        """估算文本的 token 数（粗略，中文偏保守）"""
        if not text:
            return 0
        return int(len(text) / self.CHARS_PER_TOKEN)

    def get_context_limit(self) -> int:
        """获取当前模型的上下文窗口限制"""
        context_limit, _ = _resolve_model_spec(self.model)
        return context_limit

    def get_max_output_tokens(self) -> int:
        """获取当前模型的最大输出 token 限制"""
        _, max_output = _resolve_model_spec(self.model)
        return max_output

    def clamp_max_tokens(self, max_tokens: int) -> int:
        """将 max_tokens 限制在模型允许范围内（下限 1，上限模型限制）"""
        limit = self.get_max_output_tokens()

        # 下限保护：至少 1
        if max_tokens <= 0:
            logger.warning(f"Invalid max_tokens={max_tokens}, using default 1024")
            return 1024

        # 上限保护：不超过模型上限
        if max_tokens > limit:
            logger.info(f"Clamping max_tokens from {max_tokens} to {limit} (model limit)")
            return limit

        return max_tokens

    def _load_all_agents(self, compact: bool = False) -> List[Dict]:
        """
        加载所有 agent 配置

        Args:
            compact: 精简模式，仅返回 id 和 name，不加载 full_content 和 description

        Returns:
            List[Dict]: agent 列表
        """
        agents = []
        if not self.agents_dir or not os.path.exists(self.agents_dir):
            return agents

        for filename in os.listdir(self.agents_dir):
            if filename.endswith('.md'):
                # 精简模式：仅从文件名提取 id 和 name，不读取文件内容
                if compact:
                    agent_id = filename.replace('.md', '')
                    agents.append({'id': agent_id, 'name': agent_id})
                else:
                    file_path = os.path.join(self.agents_dir, filename)
                    agent_info = self._parse_agent_file(file_path)
                    if agent_info:
                        agents.append(agent_info)

        return agents

    def _parse_agent_file(self, file_path: str) -> Optional[Dict]:
        """
        解析 agent 配置文件

        Args:
            file_path: agent 文件路径

        Returns:
            Optional[Dict]: agent 信息
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 提取 frontmatter
            frontmatter = {}
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    fm_text = parts[1].strip()
                    for line in fm_text.split('\n'):
                        if ':' in line:
                            key, value = line.split(':', 1)
                            frontmatter[key.strip()] = value.strip().strip('"')

            # 提取文件名作为 ID
            filename = os.path.basename(file_path)
            agent_id = filename.replace('.md', '')

            return {
                'id': agent_id,
                'name': frontmatter.get('name', agent_id),
                'description': frontmatter.get('description', ''),
                'model': frontmatter.get('model', 'inherit'),
                'full_content': content
            }
        except Exception:
            return None

    @staticmethod
    def _parse_dsml_content(content: str) -> Tuple[str, List[Dict]]:
        """解析 DeepSeek DSML 格式的工具调用，从文本中提取并清除 DSML 标签。

        DeepSeek 模型在某些 API 网关下无法使用标准 function calling，
        会在 msg.content 中输出 DSML 格式的工具调用标签，例如：
            <｜DSML｜function_calls｜>
            <｜DSML｜invoke name="web_search"｜>
            <｜DSML｜parameter name="query" string="true">搜索关键词</｜DSML｜parameter>
            <｜DSML｜parameter name="max_results" string="false">3</｜DSML｜parameter>
            </｜DSML｜invoke>
            </｜DSML｜function_calls｜>

        以及工具结果标签：
            <｜DSML｜invoke_result name="web_search"｜>
            <｜DSML｜content｜>...结果...</｜DSML｜content｜>
            </｜DSML｜invoke_result｜>

        同时也处理 <function_results> 等旧式标签。

        Args:
            content: 原始 LLM 响应文本

        Returns:
            Tuple[str, List[Dict]]: (清理后的纯文本, DSML解析出的工具调用列表)
        """
        if not content:
            return content, []

        # DSML 使用全角竖线 ｜ (U+FF5C) 而非 ASCII |
        DSML_PIPE = '\uff5c'

        # 如果内容中不包含 DSML 标记，直接返回
        if 'DSML' not in content and 'function_calls' not in content and 'invoke_result' not in content:
            return content, []

        tool_calls = []

        # 1. 解析 DSML invoke 块，提取工具调用
        # 匹配模式：<｜DSML｜invoke name="xxx"｜> ... </｜DSML｜invoke>
        # 同时兼容全角和半角竖线
        invoke_pattern = re.compile(
            r'<[|\uff5c]DSML[|\uff5c]invoke\s+name=["\'](\w+)["\'][|\uff5c]>(.*?)</[|\uff5c]DSML[|\uff5c]invoke[|\uff5c]>',
            re.DOTALL
        )

        # 解析参数模式：<｜DSML｜parameter name="xxx" string="true">值</｜DSML｜parameter>
        param_pattern = re.compile(
            r'<[|\uff5c]DSML[|\uff5c]parameter\s+name=["\'](\w+)["\'](?:\s+string=["\'](\w+)["\'])?[|\uff5c]>(.*?)</[|\uff5c]DSML[|\uff5c]parameter[|\uff5c]>',
            re.DOTALL
        )

        for match in invoke_pattern.finditer(content):
            tool_name = match.group(1)
            invoke_body = match.group(2)

            # 提取参数
            arguments = {}
            for param_match in param_pattern.finditer(invoke_body):
                param_name = param_match.group(1)
                param_value_str = param_match.group(3).strip()
                # 尝试解析参数值
                try:
                    arguments[param_name] = json.loads(param_value_str)
                except (json.JSONDecodeError, ValueError):
                    arguments[param_name] = param_value_str

            tool_calls.append({
                "id": f"dsml_{len(tool_calls)}",
                "name": tool_name,
                "arguments": json.dumps(arguments, ensure_ascii=False),
            })

        # 2. 清理所有 DSML 相关标签
        # 匹配所有 DSML 标签（开闭标签），兼容全角/半角竖线
        dsml_tag_pattern = re.compile(
            r'</?[|\uff5c]DSML[|\uff5c][^>]*[|\uff5c]>',
            re.DOTALL
        )

        # 匹配 <function_results>...</function_results> 旧式标签
        function_results_pattern = re.compile(
            r'<function_results>.*?</function_results>',
            re.DOTALL
        )

        # 匹配 <thinking>...</thinking> 标签（DeepSeek Reasoner 输出）
        thinking_pattern = re.compile(
            r'<thinking>.*?</thinking>',
            re.DOTALL
        )

        cleaned = content
        cleaned = dsml_tag_pattern.sub('', cleaned)
        cleaned = function_results_pattern.sub('', cleaned)
        cleaned = thinking_pattern.sub('', cleaned)

        # 清理残留的空行（连续3个以上空行压缩为2个）
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = cleaned.strip()

        if tool_calls:
            tool_names = [tc['name'] for tc in tool_calls]
            logger.info(f"DSML parser extracted {len(tool_calls)} tool calls: {tool_names}")

        return cleaned, tool_calls

    def _build_stream_messages(
        self,
        message: str,
        conversation_history: List[Dict],
        _extra_command: Optional[str],
        agent_name: str,
        tools: Optional[List[Dict]],
        skip_agent_list: bool
    ) -> List[Dict]:
        """
        构建流式调用所需的消息列表

        Args:
            message: 用户消息
            conversation_history: 对话历史
            _extra_command: 保留接口兼容，当前未使用
            agent_name: Agent 名称
            tools: 工具定义列表（保留接口兼容，不影响消息构建）
            skip_agent_list: 跳过全量 Agent 列表注入

        Returns:
            List[Dict]: OpenAI 格式的消息列表
        """
        system_prompt = self._build_system_prompt(agent_name, skip_agent_list=skip_agent_list)
        return self._build_messages(system_prompt, conversation_history, message)

    def _parse_stream_chunk(
        self,
        chunk: Any,
        collected_tool_calls: Optional[List[Dict]] = None
    ) -> Generator[Dict, None, None]:
        """
        解析单个 SSE 流式 chunk

        Args:
            chunk: API 返回的流式 chunk 对象
            collected_tool_calls: 收集工具调用的列表（预留，当前流式模式不返回 tool_calls）

        Yields:
            Dict: text / usage 事件
        """
        if not chunk.choices:
            return

        delta = chunk.choices[0].delta
        finish_reason = getattr(chunk.choices[0], 'finish_reason', None)

        # 文本内容
        if delta.content:
            yield {
                "type": "text",
                "content": delta.content
            }

        # 提取 token 使用统计（最后一个 chunk）
        if finish_reason:
            logger.info(f"LLM stream finish_reason: {finish_reason}")
        if hasattr(chunk, 'usage') and chunk.usage:
            yield {
                "type": "usage",
                "input_tokens": chunk.usage.prompt_tokens or 0,
                "output_tokens": chunk.usage.completion_tokens or 0
            }

    def _handle_non_streaming_response(
        self,
        response: Any
    ) -> Generator[Dict, None, None]:
        """
        处理非流式 LLM 响应（含标准 tool_calls 和 DSML 格式工具调用回退）

        Args:
            response: API 返回的非流式响应对象

        Yields:
            Dict: text / tool_call_delta / usage 事件
        """
        if not response.choices:
            raise RuntimeError("LLM returned empty choices")

        choice = response.choices[0]
        msg = choice.message

        logger.info(f"LLM non-streaming finish_reason: {choice.finish_reason}")

        # 检查标准 tool_calls 和 DSML 格式的工具调用
        has_standard_tool_calls = hasattr(msg, 'tool_calls') and msg.tool_calls

        # 解析 DSML 格式（DeepSeek 模型可能将工具调用输出在 content 中）
        raw_content = msg.content or ""
        cleaned_content, dsml_tool_calls = self._parse_dsml_content(raw_content)

        # 如果解析出 DSML 工具调用，说明 API 网关不支持标准 function calling
        if dsml_tool_calls:
            logger.info(f"DSML fallback: extracted {len(dsml_tool_calls)} tool calls from content "
                       f"(standard tool_calls={'yes' if has_standard_tool_calls else 'no'})")

        # 输出清理后的文本内容
        if cleaned_content:
            yield {
                "type": "text",
                "content": cleaned_content
            }

        # 标准工具调用（优先）
        if has_standard_tool_calls:
            logger.info(f"LLM returned {len(msg.tool_calls)} tool_calls")
            for i, tc in enumerate(msg.tool_calls):
                yield {
                    "type": "tool_call_delta",
                    "tool_call": {
                        "index": i,
                        "id": tc.id or "",
                        "name": tc.function.name or "",
                        "arguments": tc.function.arguments or "",
                    }
                }
        # DSML 工具调用回退（当标准 tool_calls 为空时使用）
        elif dsml_tool_calls:
            for i, tc in enumerate(dsml_tool_calls):
                yield {
                    "type": "tool_call_delta",
                    "tool_call": {
                        "index": i,
                        "id": tc["id"],
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    }
                }

        # token 使用统计
        if hasattr(response, 'usage') and response.usage:
            yield {
                "type": "usage",
                "input_tokens": response.usage.prompt_tokens or 0,
                "output_tokens": response.usage.completion_tokens or 0
            }

    def _build_api_kwargs(
        self,
        messages: List[Dict],
        max_tokens: int,
        tools: Optional[List[Dict]]
    ) -> Tuple[Dict, bool]:
        """
        构建 API 调用参数

        Args:
            messages: 消息列表
            max_tokens: 最大 token 数
            tools: 工具定义列表

        Returns:
            Tuple[Dict, bool]: (调用参数字典, 是否使用流式)
        """
        use_streaming = not tools

        call_kwargs = {
            'model': self.model,
            'max_tokens': self.clamp_max_tokens(max_tokens),
            'messages': messages,
            'stream': use_streaming,
        }

        if tools:
            call_kwargs['tools'] = tools
            call_kwargs['tool_choice'] = 'auto'
            tool_names = [t.get('function', {}).get('name', t.get('name', '?')) for t in tools]
            logger.info(f"LLM API call (non-streaming) with {len(tools)} tools: {tool_names[:10]}...")
        else:
            logger.info("LLM API call (streaming) without tools")
            call_kwargs['stream_options'] = {'include_usage': True}

        return call_kwargs, use_streaming

    def call_stream(
        self,
        message: str,
        conversation_history: List[Dict],
        extra_command: Optional[str],
        agent_name: str,
        max_tokens: int = MAX_TOKENS_EXTENDED,
        tools: Optional[List[Dict]] = None,
        skip_agent_list: bool = False
    ) -> Generator[Dict, None, None]:
        """
        调用 LLM API 并流式返回结果（支持重试）

        Args:
            message: 用户消息
            conversation_history: 对话历史
            extra_command: 额外的命令行参数
            agent_name: Agent 名称
            max_tokens: 最大 token 数量
            tools: 工具定义列表（OpenAI function calling 格式）
            skip_agent_list: 跳过全量 Agent 列表注入（OpenHarness 模式）

        Yields:
            Dict: 包含 type 和 content/data/message 的字典
        """
        last_error = None
        rate_limit_retries = 0
        attempt = 0
        yielded_content = 0  # 已向调用方产出的内容事件数（text/tool_call_delta）

        while True:
            attempt += 1
            try:
                # 构建消息列表
                messages = self._build_stream_messages(
                    message, conversation_history, extra_command,
                    agent_name, tools, skip_agent_list
                )

                # 构建 API 调用参数
                call_kwargs, use_streaming = self._build_api_kwargs(messages, max_tokens, tools)

                # 关键：部分 API（如智谱 GLM-5）流式模式不支持 function calling，
                # 当有 tools 时使用非流式调用，确保 tool_calls 正确返回。
                # 全局并发信号量收敛并行度，避免瞬时打爆 tpm 配额。
                with _LLM_CALL_SEMAPHORE:
                    if use_streaming:
                        # 流式调用（无 tools 时）
                        stream = self.client.chat.completions.create(**call_kwargs)
                        for chunk in stream:
                            for event in self._parse_stream_chunk(chunk):
                                if event.get("type") in ("text", "tool_call_delta"):
                                    yielded_content += 1
                                yield event
                    else:
                        # 非流式调用（有 tools 时）
                        # GLM-5 等模型流式模式不返回 tool_calls，必须用非流式
                        response = self.client.chat.completions.create(**call_kwargs)
                        yield from self._handle_non_streaming_response(response)

                # 完成
                yield {
                    "type": "done"
                }

                # 成功完成，退出重试循环
                return

            except Exception as e:
                last_error = e
                # 尝试提取响应体内容
                error_detail = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_detail = f"{e} | body: {e.response.text[:500]}"
                    except Exception:
                        pass
                # 提取 httpx 错误体
                if hasattr(e, 'body') and e.body:
                    try:
                        error_detail += f" | error_body: {str(e.body)[:500]}"
                    except Exception:
                        pass
                logger.warning(
                    f"LLM API stream call failed (attempt {attempt}/{RETRY_MAX_ATTEMPTS}): {error_detail}"
                    f" | model={self.model}"
                    f" | max_tokens={self.clamp_max_tokens(max_tokens)}"
                    f" | context_limit={self.get_context_limit()}"
                )

                # 已产出部分内容则禁止重试：重发会从零重新流式输出，
                # 客户端会把「半截旧答案 + 完整新答案」拼接显示成重复内容
                if yielded_content:
                    logger.error(
                        f"LLM API stream interrupted after partial output "
                        f"({yielded_content} content events); not retrying: {error_detail}"
                    )
                    raise

                is_rate_limit = _is_rate_limit_error(e)
                should_retry = (
                    (attempt < RETRY_MAX_ATTEMPTS)
                    or (is_rate_limit and rate_limit_retries < RATE_LIMIT_MAX_EXTRA_RETRIES)
                )
                if not should_retry:
                    break

                if is_rate_limit:
                    rate_limit_retries += 1
                    wait_seconds = _rate_limit_backoff(e, rate_limit_retries)
                    retry_message = (
                        f"LLM API 触发限流(429)，{wait_seconds:.0f} 秒后进行第 "
                        f"{attempt + rate_limit_retries + 1} 次重试..."
                    )
                else:
                    wait_seconds = RETRY_INTERVAL
                    retry_message = f"LLM API 调用失败，{RETRY_INTERVAL} 秒后进行第 {attempt + 1} 次重试..."

                # 发送重试事件通知前端
                yield {
                    "type": "api_retry",
                    "attempt": attempt,
                    "max_attempts": RETRY_MAX_ATTEMPTS,
                    "message": retry_message
                }

                logger.info(retry_message)
                time.sleep(wait_seconds)

        # 全部重试失败
        error_message = f"LLM API stream call failed after {RETRY_MAX_ATTEMPTS} attempts: {str(last_error)}"
        logger.error(error_message, exc_info=True)
        yield {
            "type": "error",
            "message": error_message
        }

    def _build_system_prompt(
        self,
        agent_name: str,
        skip_agent_list: bool = False
    ) -> str:
        """
        构建系统提示，包含所有可用 agents 信息

        Args:
            agent_name: 指定的 agent 名称（可选）
            skip_agent_list: 跳过全量 Agent 列表注入（OpenHarness 已通过 system_prompt 定义角色）

        Returns:
            str: 系统提示字符串
        """
        system_parts = []

        # 1. 基础角色定义
        if skip_agent_list:
            # OpenHarness 模式：Agent 角色已由 system_prompt 定义，仅注入最小上下文
            system_parts.append("You are a helpful AI assistant.")
        elif agent_name and agent_name != 'default':
            # 指定了特定 Agent 时，跳过全量 Agent 列表，直接注入该 Agent 指令
            system_parts.append("You are a helpful AI assistant.")
        else:
            base_role = """You are a helpful AI assistant.

## Agent Team Mode

You have access to a team of specialized agents. Based on the user's request, select the most appropriate agent role.

### Available Agents:"""
            system_parts.append(base_role)

            # 2. 加载所有 agents（精简格式：仅名称和 ID，不加载描述以节省上下文）
            all_agents = self._load_all_agents(compact=True)
            if all_agents:
                # 每行一个，精简格式
                agent_lines = [f"- `{a['id']}`: {a['name']}" for a in all_agents]
                system_parts.append('\n'.join(agent_lines))

            # 3. Agent 选择指引（精简版）
            agent_guidance = """

Select the most appropriate agent based on the user's request. If no specific agent fits, respond as the default assistant."""
            system_parts.append(agent_guidance)

        # 4. 如果指定了特定 agent，加载其完整指令
        if agent_name and agent_name != 'default':
            agent_content = self._get_agent_full_instructions(agent_name)
            if agent_content:
                system_parts.append("\n\n## Active Agent Instructions\n")
                system_parts.append(f"Please adopt the following agent role for this conversation:\n\n{agent_content}")

        # 5. 注入当前日期信息
        current_date = datetime.now()
        date_info = f"""

## Current Date & Time

**Current Date**: {current_date.strftime("%Y年%m月%d日")}
**Current Time**: {current_date.strftime("%H:%M:%S")}
**Weekday**: {['周一', '周二', '周三', '周四', '周五', '周六', '周日'][current_date.weekday()]}

When generating reports, timelines, mermaid diagrams, or any content involving dates, please use the current date ({current_date.strftime("%Y年%m月%d日")}) instead of outdated dates."""

        system_parts.append(date_info)

        return "\n".join(system_parts)

    def _get_agent_full_instructions(self, agent_name: str) -> Optional[str]:
        """
        获取 Agent 的完整指令内容

        Args:
            agent_name: Agent 名称

        Returns:
            Optional[str]: Agent 完整内容
        """
        if not self.agents_dir or not agent_name:
            return None

        agent_config_path = os.path.join(self.agents_dir, f"{agent_name}.md")
        if os.path.exists(agent_config_path):
            try:
                with open(agent_config_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception:
                pass

        return None

    def _build_messages(
        self,
        system_prompt: str,
        conversation_history: List[Dict],
        current_message: str
    ) -> List[Dict]:
        """
        构建消息列表（OpenAI 格式）

        Args:
            system_prompt: 系统提示
            conversation_history: 对话历史
            current_message: 当前消息

        Returns:
            List[Dict]: 消息列表
        """
        messages = []

        # 添加系统提示（OpenAI 格式）
        messages.append({
            "role": "system",
            "content": system_prompt
        })

        # 添加对话历史
        if conversation_history:
            for entry in conversation_history:
                role = entry.get("role", "")
                content = entry.get("content", "")

                if role == "system":
                    # 合并到已有的 system 消息中
                    if messages and messages[0].get("role") == "system":
                        messages[0]["content"] += "\n\n" + content
                    else:
                        messages.insert(0, {"role": "system", "content": content})
                elif role == "tool":
                    # 保留 tool 消息（function calling 结果）
                    messages.append({
                        "role": "tool",
                        "tool_call_id": entry.get("tool_call_id", ""),
                        "content": content or ""
                    })
                elif role in ["user", "assistant"]:
                    # 保留 assistant 的 tool_calls（如果有）
                    msg = {"role": role, "content": content}
                    if role == "assistant" and entry.get("tool_calls"):
                        msg["tool_calls"] = entry["tool_calls"]
                        msg["content"] = content or None  # tool_calls 时 content 可为 None
                    messages.append(msg)

        # 添加当前消息
        messages.append({
            "role": "user",
            "content": current_message
        })

        # 自动压缩：如果估算 token 超过上下文窗口的 80%，截断早期历史
        # 使用模型实际的最大输出 token 配置，而非硬编码值
        messages = self._compress_if_needed(messages, max_tokens=self.get_max_output_tokens())

        return messages

    def _compress_if_needed(
        self,
        messages: List[Dict],
        max_tokens: int = MAX_TOKENS_EXTENDED,
        reserved_ratio: float = 0.8
    ) -> List[Dict]:
        """
        自动压缩消息列表以适配上下文窗口

        Args:
            messages: 消息列表
            max_tokens: 输出 token 预留
            reserved_ratio: 上下文窗口使用比例上限

        Returns:
            List[Dict]: 压缩后的消息列表
        """
        context_limit = self.get_context_limit()
        # 实际输出 token 上限
        actual_max_tokens = min(max_tokens, self.get_max_output_tokens())
        # 可用输入 token = 总上下文 * 比例 - 输出预留
        available_tokens = int(context_limit * reserved_ratio) - actual_max_tokens
        if available_tokens < 1000:
            # 至少保留 1000 token 给输入
            available_tokens = 1000

        # 估算当前总 token
        total_text = ''
        for msg in messages:
            content = msg.get('content') or ''
            total_text += content
            if msg.get('tool_calls'):
                total_text += str(msg['tool_calls'])

        estimated_tokens = self.estimate_tokens(total_text)

        if estimated_tokens <= available_tokens:
            return messages

        logger.warning(
            f"Context overflow detected: estimated {estimated_tokens} tokens > "
            f"available {available_tokens} tokens. Compressing history..."
        )

        # 只允许删除早期历史，绝不删除或裁剪当前用户提示词。
        if len(messages) <= 2:
            raise ContextWindowExceededError(
                f"context_window_exceeded: input requires about {estimated_tokens} tokens, "
                f"but only {available_tokens} input tokens are available"
            )

        # 分离 system 消息和其余消息
        system_msgs = [m for m in messages if m.get('role') == 'system']
        other_msgs = [m for m in messages if m.get('role') != 'system']

        # 保留最后一条非 system 消息（当前请求），逐步移除更早的历史。
        if not other_msgs:
            raise ContextWindowExceededError("context_window_exceeded: system prompt is too large")

        while len(other_msgs) > 1 and estimated_tokens > available_tokens:
            removed = other_msgs.pop(0)
            removed_text = removed.get('content') or ''
            if removed.get('tool_calls'):
                removed_text += str(removed['tool_calls'])
            estimated_tokens -= self.estimate_tokens(removed_text)

        if estimated_tokens > available_tokens:
            raise ContextWindowExceededError(
                f"context_window_exceeded: current prompt requires about {estimated_tokens} tokens, "
                f"but only {available_tokens} input tokens are available"
            )

        result = system_msgs + other_msgs
        logger.info(
            f"Compressed messages: {len(messages)} -> {len(result)}, "
            f"estimated tokens: {estimated_tokens}"
        )
        return result

    def call_sync(
        self,
        message: str,
        system_prompt: str = None,
        max_tokens: int = MAX_TOKENS_EXTENDED,
        retry_callback: Optional[Callable[[int, int, str], None]] = None,
        max_attempts: Optional[int] = None,
        timeout: Optional[float] = None,
        reject_truncated: bool = False,
        empty_content_ok: bool = False,
    ) -> str:
        """
        调用 LLM API 同步返回结果（用于最终报告生成等长输出场景）

        Args:
            message: 用户消息/提示词
            system_prompt: 系统提示（可选）
            max_tokens: 最大 token 数量
            retry_callback: 重试回调函数，参数为 (attempt, max_attempts, message)
            max_attempts: 覆盖默认重试次数；用于可降级的报告合成等路径快速失败
            timeout: 覆盖 OpenAI client 默认超时；用于最终报告等长输出路径
            reject_truncated: provider 因输出 token 上限结束时将响应视为失败
            empty_content_ok: 空响应由调用方按非致命降级处理，不记录失败堆栈

        Returns:
            str: LLM 的完整响应文本
        """
        last_error = None
        attempts = max(1, max_attempts or RETRY_MAX_ATTEMPTS)
        rate_limit_retries = 0
        attempt = 0

        while True:
            attempt += 1
            call_started_at = time.perf_counter()
            response = None
            try:
                # 构建消息列表
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": message})

                # 检查上下文是否超限，超限时压缩 message 内容
                messages = self._compress_if_needed(messages, max_tokens=max_tokens)

                # 调试：记录请求详情
                clamped_max_tokens = self.clamp_max_tokens(max_tokens)
                msg_roles = [m.get('role', '?') for m in messages]
                msg_sizes = [len(str(m.get('content', '') or '')) for m in messages]
                logger.info(
                    f"LLM sync call: model={self.model}, max_tokens={clamped_max_tokens}, "
                    f"messages={len(messages)}, roles={msg_roles}, sizes={msg_sizes}"
                )

                # 调用 API（全局并发信号量收敛并行度，避免打爆 tpm 配额）
                with _LLM_CALL_SEMAPHORE:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        max_tokens=self.clamp_max_tokens(max_tokens),
                        messages=messages,
                        stream=False,
                        timeout=timeout,
                    )

                # 提取响应内容
                if response.choices and response.choices[0].message.content:
                    finish_reason = getattr(response.choices[0], 'finish_reason', None)
                    if reject_truncated and finish_reason in {'length', 'max_tokens'}:
                        raise RuntimeError(
                            f'LLM response truncated (finish_reason={finish_reason})'
                        )
                    raw_content = response.choices[0].message.content
                    # 清理 DSML 标签（DeepSeek 模型可能在 content 中输出工具调用标签）
                    cleaned_content, _ = self._parse_dsml_content(raw_content)
                    usage = getattr(response, "usage", None)
                    input_tokens = getattr(usage, "prompt_tokens", None)
                    output_tokens = getattr(usage, "completion_tokens", None)
                    if input_tokens is None:
                        input_tokens = self.estimate_tokens(
                            "".join(str(m.get("content") or "") for m in messages)
                        )
                    if output_tokens is None:
                        output_tokens = self.estimate_tokens(cleaned_content)
                    self._record_usage(
                        input_tokens,
                        output_tokens,
                        time.perf_counter() - call_started_at,
                    )
                    return cleaned_content
                if empty_content_ok:
                    usage = getattr(response, "usage", None)
                    input_tokens = getattr(usage, "prompt_tokens", None)
                    if input_tokens is None:
                        input_tokens = self.estimate_tokens(
                            "".join(str(m.get("content") or "") for m in messages)
                        )
                    output_tokens = getattr(usage, "completion_tokens", None) or 0
                    self._record_usage(
                        input_tokens,
                        output_tokens,
                        time.perf_counter() - call_started_at,
                    )
                    logger.info(
                        "LLM returned empty content; using the caller's non-fatal fallback "
                        "| model=%s max_tokens=%s",
                        self.model,
                        clamped_max_tokens,
                    )
                    return ""
                raise RuntimeError("LLM returned empty content")

            except ContextWindowExceededError:
                logger.error(
                    "LLM request rejected because the prompt exceeds the model context window: model=%s",
                    self.model,
                )
                raise
            except Exception as e:
                last_error = e
                # 记录详细错误信息（含请求体大小和响应体）
                total_chars = sum(len(str(m.get('content', ''))) for m in messages)
                estimated_input_tokens = self.estimate_tokens(
                    ''.join(str(m.get('content', '') or '') for m in messages)
                )
                usage = getattr(response, "usage", None)
                self._record_usage(
                    getattr(usage, "prompt_tokens", None) or estimated_input_tokens,
                    getattr(usage, "completion_tokens", None) or 0,
                    time.perf_counter() - call_started_at,
                    failed=True,
                )
                error_detail = str(e)
                # 尝试提取响应体内容
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_detail = f"{e} | body: {e.response.text[:500]}"
                    except Exception:
                        pass
                logger.warning(
                    f"LLM API sync call failed (attempt {attempt}/{attempts}): {error_detail}"
                    f" | messages_count={len(messages)} total_chars={total_chars}"
                    f" | estimated_input_tokens={estimated_input_tokens}"
                    f" | max_tokens={self.clamp_max_tokens(max_tokens)}"
                    f" | model={self.model}"
                    f" | context_limit={self.get_context_limit()}"
                )

                is_rate_limit = _is_rate_limit_error(e)
                # 429 限流：独立于调用方 max_attempts 获得额外重试预算（指数退避）。
                # 其他错误仍遵循 max_attempts 语义（如子任务分析 max_attempts=1 快速失败）。
                should_retry = (
                    (attempt < attempts)
                    or (is_rate_limit and rate_limit_retries < RATE_LIMIT_MAX_EXTRA_RETRIES)
                )
                if not should_retry:
                    break

                if is_rate_limit:
                    rate_limit_retries += 1
                    wait_seconds = _rate_limit_backoff(e, rate_limit_retries)
                    retry_message = (
                        f"LLM API 触发限流(429)，{wait_seconds:.0f} 秒后进行第 "
                        f"{attempt + rate_limit_retries + 1} 次重试..."
                    )
                else:
                    wait_seconds = RETRY_INTERVAL
                    retry_message = f"LLM API 调用失败，{RETRY_INTERVAL} 秒后进行第 {attempt + 1} 次重试..."
                logger.info(retry_message)

                # 调用回调通知前端
                if retry_callback:
                    try:
                        retry_callback(attempt, attempts, retry_message)
                    except Exception as callback_error:
                        logger.warning(f"Retry callback failed: {callback_error}")

                time.sleep(wait_seconds)

        # 全部重试失败
        error_message = f"LLM API sync call failed after {attempts} attempts: {str(last_error)}"
        if last_error and getattr(last_error, "__traceback__", None):
            logger.error(
                error_message,
                exc_info=(type(last_error), last_error, last_error.__traceback__),
            )
        else:
            logger.error(error_message)
        raise RuntimeError(error_message)


