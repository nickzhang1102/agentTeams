"""
数据模型定义

使用原生 SQLAlchemy 2.0 声明式映射。

迁移要点：
- db.Model → Base (DeclarativeBase)
- db.Column → mapped_column()
- 类型注解使用 Mapped[类型]
- relationship 保持不变

模型清单（35 个）：
├── 系统配置类
│   ├── AgentConfig      - Agent 配置与统计
│   ├── AgentCategory    - Agent 分类（DB 动态聚合）
│   ├── SystemConfig     - 系统配置
│   ├── ToolCallLog      - 工具调用日志
│   └── BackfillTask     - 能力补全后台任务
│
├── 用户类
│   └── User             - 用户（含密码安全、账户锁定）
│
├── 对话类
│   ├── Conversation     - 对话（含分享、分类、状态）
│   ├── Message          - 统一消息表
│   ├── File             - 文件
│   └── ContentTranslation - 历史 AI 内容翻译缓存
│
├── Integration 集成类
│   ├── IntegrationClient - 外部系统身份与能力注册
│   ├── IntegrationAccessOperation - 本地访问撤销操作状态
│   ├── AgentTeamsLaunch   - 兼容的启动幂等记录（逐步迁移到通用核心）
│   └── AgentTeamsEmbedToken - Agent Teams 短期嵌入访问令牌
│
├── Leader 类
│   ├── LeaderSession    - Leader 会话
│   ├── LeaderWorkflowCancellation - 跨 worker 取消墓碑
│   ├── LeaderAgentResult - Agent 执行结果
│   ├── LeaderFinalReport - 最终报告
│   └── LeaderReportRating - Leader 报告评分
│
├── 决策运行类
│   ├── DecisionRun      - 一次决策运行的跨条目身份与生命周期
│   ├── DecisionEvidence - 决策证据条目
│   ├── DecisionClaim    - 证据支撑的结论声明
│   ├── DecisionClaimEvidence - 声明与证据的多对多绑定
│   ├── DecisionEvidenceMetrics - 证据质量指标
│   └── SecurityLog      - 安全日志（登录安全、集成审计）
│
├── OpenHarness 类
│   └── HarnessSessionMapping - 会话映射
│
├── Agent 权限类
│   ├── AgentMcpPermission - MCP 工具权限
│   └── AgentPriorityRule - 优先级规则
│
├── Agent 组合包类
│   ├── AgentPack        - Agent 组合包
│   └── WorkflowTemplate - 工作流模板
│
├── 知识库类
│   ├── KnowledgeDocument - 知识库文档
│   └── KnowledgeCategory - 知识库分类
│
└── 记忆与向量类
    ├── AgentMemory      - 用户长期记忆
    ├── NodeEmbedding    - 知识图谱节点向量
    └── LLMModel         - LLM 模型配置
"""
from datetime import datetime
from typing import Optional, List
from threading import local
from uuid import UUID, uuid4

from sqlalchemy import (
    String, Text, Integer, BigInteger, Float, Boolean, DateTime,
    Numeric, JSON, ForeignKey, Index, CheckConstraint, event,
    UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB, UUID as PG_UUID
from sqlalchemy.orm import (
    Mapped, mapped_column, relationship, validates, backref
)
from sqlalchemy.ext.hybrid import hybrid_property

from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import string

from db import Base
from utils.credential_encryption import EncryptedText
from utils.time_utils import utcnow_naive

# pgvector 向量列类型（需要 pgvector Python 包）
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None  # pgvector 未安装时优雅降级

# 线程本地递归守卫，用于 User 模型事件监听器
_event_recursion_guard = local()


# ==================== 系统配置类 ====================

class AgentCategory(Base):
    """Agent 分类元数据表

    替代 agent_category_service.py 中的 CATEGORY_META 硬编码。
    """
    __tablename__ = 'agent_categories'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(10))
    color: Mapped[Optional[str]] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f'<AgentCategory {self.key}>'


class AgentConfig(Base):
    """Agent 配置与统计表

    存储每个 Agent 的完整信息：

    基本信息（从 .md 文件同步）：
    - agent_id: 唯一标识符（对应 .md 文件名）
    - name: Agent 名称
    - description: Agent 描述
    - model: 使用的模型（inherit 或具体模型名）

    文件状态：
    - file_path: .md 文件的完整路径
    - file_exists: 文件是否存在（同步时检测）

    启用控制：
    - is_enabled: 是否启用（Admin 可切换）
    - priority: 优先级（用于排序和调度）

    统计数据：
    - total_calls: 总调用次数
    - success_calls: 成功次数
    - failed_calls: 失败次数
    - total_tokens: Token 消耗总和
    - avg_execution_time: 平均执行时间（秒）
    """
    __tablename__ = 'agent_configs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    file_exists: Mapped[bool] = mapped_column(Boolean, default=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=30, server_default='30')

    # 基本信息（从 .md 文件同步）
    name: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    model: Mapped[Optional[str]] = mapped_column(String(50))

    # 统计数据
    total_calls: Mapped[int] = mapped_column(Integer, default=0)
    success_calls: Mapped[int] = mapped_column(Integer, default=0)
    failed_calls: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    avg_execution_time: Mapped[float] = mapped_column(Float, default=0.0)

    # 存储来源
    source: Mapped[str] = mapped_column(String(20), default='file')        # "file" | "db"
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)         # 系统预设 vs 用户自建
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    # Agent 内容（DB 直接存储）
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # system prompt 全文
    role: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    persona: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expertise: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approach: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 能力声明
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # "medical"|"business"|"finance"|"custom"|None
    capabilities: Mapped[Optional[list]] = mapped_column(PG_JSONB, default=list)  # JSONB 数组
    skill_level: Mapped[int] = mapped_column(Integer, default=3)           # 1-5
    tags: Mapped[Optional[list]] = mapped_column(PG_JSONB, default=list)    # JSONB 数组
    preferred_contexts: Mapped[Optional[list]] = mapped_column(PG_JSONB, default=list)  # JSONB 数组

    # 展示
    portrait_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    def __repr__(self) -> str:
        return f'<AgentConfig {self.agent_id}>'

    def to_dict(self, content: Optional[str] = None) -> dict:
        result = {
            'id': self.id, 'agent_id': self.agent_id, 'name': self.name,
            'description': self.description, 'model': self.model,
            'is_enabled': self.is_enabled, 'file_exists': self.file_exists,
            'priority': self.priority, 'total_calls': self.total_calls,
            'success_calls': self.success_calls, 'failed_calls': self.failed_calls,
            'total_tokens': self.total_tokens,
            'avg_execution_time': self.avg_execution_time,
            'source': self.source, 'is_system': self.is_system,
            'created_by': self.created_by,
            'role': self.role, 'persona': self.persona,
            'expertise': self.expertise, 'approach': self.approach,
            'category': self.category,
            'capabilities': self.capabilities or [],
            'skill_level': self.skill_level,
            'tags': self.tags or [],
            'preferred_contexts': self.preferred_contexts or [],
            'portrait_url': self.portrait_url,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }
        if content is not None:
            result['content'] = content
        elif self.content:
            result['content'] = self.content
        return result


class SystemConfig(Base):
    """系统配置表

    存储可动态修改的系统配置项（无需重启服务）。

    主要配置类别：
    - OpenHarness 开关：OPENHARNESS_ENABLED, OPENHARNESS_TOOLS_ENABLED
    - 执行参数：MAX_AGENT_ITERATIONS, MAX_AGENT_PARALLEL
    - 超时设置：OPENHARNESS_TOOLS_TIMEOUT, OPENHARNESS_TIMEOUT
    - 存储路径：WORKSPACE_DIR

    注意：部分配置修改后需重启服务生效（如 OPENHARNESS_ENABLED）。
    """
    __tablename__ = 'system_configs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    def __repr__(self) -> str:
        return f'<SystemConfig {self.key}>'

    @property
    def is_secret(self) -> bool:
        """返回该设置是否包含凭据信息。"""
        normalized = (self.key or '').upper()
        return normalized.endswith(('_API_KEY', '_KEY', '_SECRET', '_TOKEN')) or any(
            marker in normalized
            for marker in ('_API_KEY_', '_SECRET_', '_TOKEN_', 'KEY_HASH')
        )

    def to_dict(self, reveal_sensitive: bool = False) -> dict:
        secret = self.is_secret
        value = self.value if (reveal_sensitive or not secret) else ('********' if self.value else '')
        return {
            'id': self.id, 'key': self.key, 'value': value,
            'is_secret': secret,
            'is_configured': bool(self.value) if secret else None,
            'description': self.description,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }


class ToolCallLog(Base):
    """工具调用日志表

    记录 Agent 工具调用的完整信息，用于：
    - 调试和排查问题
    - 性能分析
    - 安全审计

    字段说明：
    - tool_name: 工具名称（如 file_read, execute_code）
    - tool_input: 输入参数（JSON）
    - tool_output: 输出结果（JSON）
    - status: 执行状态（success, failed, timeout）
    - execution_time: 执行耗时（秒）
    - error_message: 错误信息（失败时记录）
    """
    __tablename__ = 'tool_call_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('conversations.id'), index=True)
    leader_session_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('leader_sessions.id'), index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tool_input: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    tool_output: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success, failed, timeout
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    execution_time: Mapped[Optional[float]] = mapped_column(Float)  # 秒
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)

    # 关系
    conversation: Mapped[Optional["Conversation"]] = relationship(backref='tool_call_logs')
    leader_session: Mapped[Optional["LeaderSession"]] = relationship(
        foreign_keys=[leader_session_id],
        overlaps="tool_call_logs"
    )

    def __repr__(self) -> str:
        return f'<ToolCallLog {self.tool_name} - {self.status}>'

    def to_dict(self) -> dict:
        return {
            'id': self.id, 'conversation_id': self.conversation_id,
            'agent_id': self.agent_id, 'tool_name': self.tool_name,
            'tool_input': self.tool_input, 'tool_output': self.tool_output,
            'status': self.status, 'error_message': self.error_message,
            'execution_time': self.execution_time,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
        }


# ==================== 用户类 ====================

class User(Base):
    """用户表

    核心用户信息：
    - username: 用户名（唯一）
    - email: 邮箱（唯一）
    - password_hash: 密码哈希（PBKDF2-SHA256）
    - is_admin: 管理员标识
    - account_type: 账户类型（human/service）
    - login_disabled: 是否禁用普通登录

    账户安全：
    - failed_login_attempts: 连续登录失败次数
    - locked_until: 锁定到期时间
    - lockout_reason: 锁定原因

    密码安全机制：
    - 使用 werkzeug.security.generate_password_hash()
    - 算法: PBKDF2 + SHA256
    - 迭代: 260,000 次
    - 盐值: 随机生成
    - 存储: pbkdf2:sha256:260000$salt$hash
    - 特性: 单向加密，无法逆向解密

    账户锁定机制：
    - 连续 5 次失败 → 锁定 15 分钟
    - 锁定期间登录提示"用户名或密码错误"（不泄露锁定状态）
    - 锁定过期自动解锁
    """
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default='editor', nullable=False, index=True)  # viewer/editor/admin
    account_type: Mapped[str] = mapped_column(String(20), default='human', nullable=False, index=True)  # human/service
    login_disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    preferred_locale: Mapped[str] = mapped_column(String(10), default='zh-CN', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # 账户锁定字段
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    lockout_reason: Mapped[Optional[str]] = mapped_column(String(255))

    # Token 版本控制（改密/刷新时递增，使旧 token 失效）
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 关系
    conversations: Mapped[List["Conversation"]] = relationship(
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    content_translations: Mapped[List["ContentTranslation"]] = relationship(
        back_populates='user',
        cascade='all, delete-orphan'
    )

    def set_password(self, password: str) -> None:
        """
        设置密码（加密存储）

        使用 werkzeug.security.generate_password_hash() 进行安全加密：
        - 算法: PBKDF2 + SHA256
        - 迭代: 260,000 次
        - 盐值: 随机生成
        - 存储: pbkdf2:sha256:260000$salt$hash
        - 特性: 单向加密，无法逆向解密

        Args:
            password: 明文密码
        """
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """
        验证密码

        使用 werkzeug.security.check_password_hash() 进行验证：
        - 从 password_hash 提取盐值和算法参数
        - 对输入密码使用相同参数计算哈希
        - 比较哈希值是否匹配
        - 防止时序攻击

        Args:
            password: 明文密码

        Returns:
            bool: 密码是否正确
        """
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        """转换为字典（不含敏感信息）"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_admin': self.is_admin,
            'role': self.role,
            'account_type': self.account_type,
            'login_disabled': self.login_disabled,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'last_login': self.last_login.isoformat() + 'Z' if self.last_login else None
        }

    def __repr__(self) -> str:
        return f'<User {self.username}>'


@event.listens_for(User.is_admin, 'set')
def _sync_user_role(target, value, oldvalue, initiator):
    """保持 is_admin 与 role 字段双向同步（带递归守卫）"""
    if getattr(_event_recursion_guard, 'in_sync', False):
        return
    _event_recursion_guard.in_sync = True
    try:
        if value and target.role != 'admin':
            target.role = 'admin'
        elif not value and target.role == 'admin':
            target.role = 'editor'
    finally:
        _event_recursion_guard.in_sync = False


@event.listens_for(User.role, 'set')
def _sync_user_is_admin(target, value, oldvalue, initiator):
    """保持 role 与 is_admin 字段双向同步（带递归守卫）"""
    if getattr(_event_recursion_guard, 'in_sync', False):
        return
    _event_recursion_guard.in_sync = True
    try:
        new_admin = (value == 'admin')
        if new_admin != target.is_admin:
            target.is_admin = new_admin
    finally:
        _event_recursion_guard.in_sync = False


# ==================== 对话类 ====================

class Conversation(Base):
    """对话表

    存储用户对话的元信息：

    基本信息：
    - title: 对话标题
    - user_id: 所属用户

    状态字段：
    - is_archived: 是否归档
    - is_review_mode: 是否评审模式（Leader 模式）
    - category: 分类（technology/business/medical/investment/science/writing/legal/education/lifestyle/other）
    - status: 状态（new/analyzing/error/completed/stopped）

    精选功能：
    - is_featured: 是否精选（展示在主页）
    - featured_order: 精选排序序号（小值优先）

    分享功能：
    - share_token: URL 安全的随机令牌，用于公开分享

    分类说明：
    - technology: 技术开发
    - business: 商业咨询
    - medical: 医疗健康
    - investment: 投资理财
    - science: 科学研究
    - writing: 写作创作
    - legal: 法律咨询
    - education: 教育培训
    - lifestyle: 生活服务
    - other: 其他
    """
    __tablename__ = 'conversations'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_review_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    share_token: Mapped[Optional[str]] = mapped_column(String(20), unique=True, index=True)
    model_override: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(String(20), default='other', index=True)
    status: Mapped[str] = mapped_column(String(20), default='new', index=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    featured_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    default_locale: Mapped[str] = mapped_column(String(10), default='zh-CN', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    # 关系
    messages: Mapped[List["Message"]] = relationship(
        backref='conversation',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    files: Mapped[List["File"]] = relationship(
        backref='conversation',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    leader_sessions: Mapped[List["LeaderSession"]] = relationship(
        backref='conversation',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    content_translations: Mapped[List["ContentTranslation"]] = relationship(
        back_populates='conversation',
        cascade='all, delete-orphan'
    )

    @staticmethod
    def generate_share_token(length: int = 12) -> str:
        """
        生成 URL 安全的随机分享令牌

        使用 secrets 模块确保随机性：
        - 字符集: A-Z, a-z, 0-9
        - 长度: 默认 12 位
        - 特性: URL 安全，无特殊字符

        Args:
            length: 令牌长度

        Returns:
            str: 随机令牌
        """
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def to_dict(self, include_share_token: bool = True) -> dict:
        """转换为字典"""
        result = {
            'id': self.id,
            'title': self.title,
            'user_id': self.user_id,
            'is_archived': self.is_archived,
            'is_review_mode': self.is_review_mode,
            'category': self.category,
            'status': self.status,
            'is_featured': self.is_featured,
            'featured_order': self.featured_order,
            'model_override': self.model_override,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None
        }
        if include_share_token:
            result['share_token'] = self.share_token
        return result

    def __repr__(self) -> str:
        return f'<Conversation {self.title or self.id}>'


class ContentTranslation(Base):
    """历史 AI 内容的持久化翻译缓存。"""
    __tablename__ = 'content_translations'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('conversations.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_locale: Mapped[str] = mapped_column(String(10), nullable=False)
    target_locale: Mapped[str] = mapped_column(String(10), nullable=False)
    translated_payload: Mapped[Optional[dict]] = mapped_column(PG_JSONB)
    status: Mapped[str] = mapped_column(String(16), default='pending', nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(32))
    model_id: Mapped[Optional[str]] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(64))
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    user: Mapped["User"] = relationship(back_populates='content_translations')
    conversation: Mapped["Conversation"] = relationship(
        back_populates='content_translations'
    )

    __table_args__ = (
        UniqueConstraint(
            'source_type',
            'source_id',
            'target_locale',
            'source_hash',
            name='uq_content_translation_source_target_hash',
        ),
        CheckConstraint(
            "source_type IN ('message', 'leader_agent_result', "
            "'leader_final_report')",
            name='ck_content_translation_source_type',
        ),
        CheckConstraint(
            "source_locale IN ('zh-CN', 'en-US')",
            name='ck_content_translation_source_locale',
        ),
        CheckConstraint(
            "target_locale IN ('zh-CN', 'en-US')",
            name='ck_content_translation_target_locale',
        ),
        CheckConstraint(
            "status IN ('pending', 'ready', 'failed')",
            name='ck_content_translation_status',
        ),
        Index(
            'idx_content_translation_source',
            'source_type',
            'source_id',
        ),
        Index(
            'idx_content_translation_recovery',
            'status',
            'lease_expires_at',
        ),
    )


class Message(Base):
    """统一消息表

    持久化对话输入/输出与 Leader 流程事件，通过 message_type 区分：

    消息类型（message_type）：
    - normal: 对话入口消息（当前为 Leader 用户问题；保留 assistant 兼容历史数据）
    - assessment: Leader 需求评估
    - question: Leader 生成的提问
    - answer: 用户回答 Leader 提问
    - team_config: 团队配置
    - progress: 执行进度
    - agent_result: Agent 执行结果
    - final_report: 最终报告
    - error: 错误信息
    - retry_counts: 重试计数

    字段说明：
    - role: 角色（user/assistant/NULL）
    - content: JSON 格式内容（{'text': '内容'} 或复杂对象）
    - leader_session_id: Leader 会话 ID（对话入口消息可为 NULL）
    - sequence_number: 排序序号（Leader 消息必填）

    Leader 消息约束：
    - leader_session_id IS NOT NULL 时 sequence_number 必填
    - (leader_session_id, sequence_number) 唯一
    """
    __tablename__ = 'messages'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey('conversations.id'), nullable=False, index=True)
    role: Mapped[Optional[str]] = mapped_column(String(20))  # user/assistant, Leader 消息为 NULL
    content: Mapped[Optional[dict]] = mapped_column(PG_JSONB)  # JSONB 格式
    raw_content: Mapped[Optional[str]] = mapped_column(Text)
    content_locale: Mapped[Optional[str]] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)

    # Leader Agent 相关字段
    leader_session_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('leader_sessions.id', ondelete='CASCADE'))
    message_type: Mapped[str] = mapped_column(String(20), default='normal', index=True)
    is_review_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    sequence_number: Mapped[Optional[int]] = mapped_column(Integer)

    # 消息编辑与分支
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    parent_message_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('messages.id'))

    # 关系
    files: Mapped[List["File"]] = relationship(backref='message', lazy='dynamic', cascade='all, delete-orphan')

    # 表级约束和索引
    __table_args__ = (
        # Leader 消息的 sequence_number 唯一性约束（部分索引）
        Index('idx_leader_message_sequence', 'leader_session_id', 'sequence_number',
              unique=True,
              postgresql_where='leader_session_id IS NOT NULL'),
        # 时间索引
        Index('idx_conversation_created', 'conversation_id', 'created_at'),
    )

    @staticmethod
    def create_normal_message(
        conversation_id: int,
        role: str,
        content: str,
        **kwargs
    ) -> "Message":
        """
        创建对话入口消息（Leader 用户问题及历史兼容数据）

        Args:
            conversation_id: 对话 ID
            role: 角色（user/assistant）
            content: 文本内容
            **kwargs: 其他字段

        Returns:
            Message: 新消息对象
        """
        return Message(
            conversation_id=conversation_id,
            role=role,
            content={'text': content},
            message_type='normal',
            **kwargs
        )

    @staticmethod
    def create_leader_message(
        conversation_id: int,
        leader_session_id: int,
        message_type: str,
        content: dict,
        sequence_number: int,
        **kwargs
    ) -> "Message":
        """
        创建 Leader 流程消息

        Args:
            conversation_id: 对话 ID
            leader_session_id: Leader 会话 ID
            message_type: 消息类型
            content: JSON 内容
            sequence_number: 排序序号
            **kwargs: 其他字段

        Returns:
            Message: 新消息对象
        """
        return Message(
            conversation_id=conversation_id,
            leader_session_id=leader_session_id,
            message_type=message_type,
            content=content,
            sequence_number=sequence_number,
            **kwargs
        )

    def get_text_content(self) -> str:
        """
        获取文本内容

        兼容处理：
        - 新格式: content={'text': '内容'}
        - 旧格式: content='内容'（字符串）
        """
        if isinstance(self.content, str):
            return self.content
        elif isinstance(self.content, dict):
            return self.content.get('text', '')
        return ''

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'role': self.role,
            'content': self.content,
            'raw_content': self.raw_content,
            'content_locale': self.content_locale,
            'leader_session_id': self.leader_session_id,
            'message_type': self.message_type,
            'is_review_mode': self.is_review_mode,
            'sequence_number': self.sequence_number,
            'edited_at': self.edited_at.isoformat() + 'Z' if self.edited_at else None,
            'parent_message_id': self.parent_message_id,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None
        }

    def __repr__(self) -> str:
        return f'<Message {self.id} type={self.message_type}>'


class File(Base):
    """文件表

    存储上传文件的元数据：
    - filename: 文件名
    - file_path: 文件存储路径
    - file_type: MIME 类型
    - file_size: 文件大小（字节）
    - version: 版本号（支持版本管理）

    关联关系：
    - conversation_id: 所属对话
    - message_id: 所属消息
    - user_id: 上传用户
    """
    __tablename__ = 'files'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('conversations.id'), nullable=True, index=True)
    message_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('messages.id'), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column(String(100))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'message_id': self.message_id,
            'user_id': self.user_id,
            'filename': self.filename,
            'file_path': self.file_path,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'version': self.version,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None
        }

    def __repr__(self) -> str:
        return f'<File {self.filename} v{self.version}>'


# ==================== 决策运行类 ====================

class DecisionRun(Base):
    """一次决策运行的跨条目身份与生命周期来源。"""

    __tablename__ = 'decision_runs'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        default=uuid4,
        nullable=False,
        unique=True,
    )
    leader_session_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey('leader_sessions.id', ondelete='SET NULL'),
        nullable=True,
        unique=True,
    )
    conversation_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey('conversations.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, default='web')
    source_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    workflow_template_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey('workflow_templates.id', ondelete='SET NULL'),
        nullable=True,
    )
    workflow_version_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    domain_profile_key: Mapped[str] = mapped_column(
        String(100), nullable=False, default='general'
    )
    domain_profile_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    state: Mapped[str] = mapped_column(String(20), nullable=False, default='queued', index=True)
    quality_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default='pending', index=True
    )
    current_stage: Mapped[str] = mapped_column(
        String(20), nullable=False, default='intake', index=True
    )
    degradation_reasons: Mapped[list] = mapped_column(
        PG_JSONB, nullable=False, default=list
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    leader_session: Mapped[Optional["LeaderSession"]] = relationship(
        backref=backref('decision_run', uselist=False)
    )
    conversation: Mapped[Optional["Conversation"]] = relationship(
        backref='decision_runs'
    )

    __table_args__ = (
        CheckConstraint(
            "source IN ('web', 'agentteams', 'api')",
            name='ck_decision_runs_source',
        ),
        CheckConstraint(
            "state IN ('queued', 'running', 'waiting_input', 'completed', 'failed', 'cancelled')",
            name='ck_decision_runs_state',
        ),
        CheckConstraint(
            "quality_status IN ('pending', 'passed', 'degraded', 'blocked')",
            name='ck_decision_runs_quality_status',
        ),
        CheckConstraint(
            "current_stage IN ('intake', 'assessment', 'team_form', 'execution', 'review', 'synthesis', 'persistence')",
            name='ck_decision_runs_current_stage',
        ),
        Index('idx_decision_runs_source_ref', 'source', 'source_ref'),
    )

    def to_dict(self) -> dict:
        return {
            'run_id': str(self.run_id),
            'source': self.source,
            'source_ref': self.source_ref,
            'state': self.state,
            'quality_status': self.quality_status,
            'current_stage': self.current_stage,
            'degradation_reasons': list(self.degradation_reasons or []),
            'error_code': self.error_code,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'started_at': self.started_at.isoformat() + 'Z' if self.started_at else None,
            'completed_at': self.completed_at.isoformat() + 'Z' if self.completed_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }


@event.listens_for(DecisionRun, 'before_insert')
@event.listens_for(DecisionRun, 'before_update')
def validate_decision_run(mapper, connection, target):
    valid_sources = {'web', 'agentteams', 'api'}
    valid_states = {'queued', 'running', 'waiting_input', 'completed', 'failed', 'cancelled'}
    valid_quality = {'pending', 'passed', 'degraded', 'blocked'}
    valid_stages = {'intake', 'assessment', 'team_form', 'execution', 'review', 'synthesis', 'persistence'}
    if target.source not in valid_sources:
        raise ValueError(f"Invalid DecisionRun source: {target.source}")
    if target.state not in valid_states:
        raise ValueError(f"Invalid DecisionRun state: {target.state}")
    if target.quality_status not in valid_quality:
        raise ValueError(f"Invalid DecisionRun quality_status: {target.quality_status}")
    if target.current_stage not in valid_stages:
        raise ValueError(f"Invalid DecisionRun current_stage: {target.current_stage}")
    reasons = target.degradation_reasons or []
    if not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons):
        raise ValueError("DecisionRun degradation_reasons must be a list of strings")
    if target.quality_status == 'degraded' and not reasons:
        raise ValueError("DecisionRun degraded quality requires at least one reason code")


class DecisionEvidence(Base):
    """供报告与所有者详情读取使用的、运行作用域内的证据快照。"""

    __tablename__ = 'decision_evidences'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    decision_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey('decision_runs.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    evidence_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    locator: Mapped[dict] = mapped_column(PG_JSONB, nullable=False, default=dict)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    passage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completeness: Mapped[str] = mapped_column(String(20), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    relevance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    subtask_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    decision_run: Mapped["DecisionRun"] = relationship(
        backref=backref('evidences', cascade='all, delete-orphan', passive_deletes=True)
    )

    __table_args__ = (
        UniqueConstraint(
            'decision_run_id', 'evidence_id', name='uq_decision_evidences_run_evidence'
        ),
        CheckConstraint(
            "source_type IN ('web', 'knowledge', 'memory', 'user_input', "
            "'tool_result', 'subtask_result', 'agent_report')",
            name='ck_decision_evidences_source_type',
        ),
        CheckConstraint(
            "completeness IN ('passage', 'snippet', 'legacy', 'unavailable')",
            name='ck_decision_evidences_completeness',
        ),
        CheckConstraint(
            'relevance_score IS NULL OR (relevance_score >= 0 AND relevance_score <= 1)',
            name='ck_decision_evidences_relevance_score',
        ),
        CheckConstraint('rank IS NULL OR rank >= 0', name='ck_decision_evidences_rank'),
        Index('idx_decision_evidences_run_source', 'decision_run_id', 'source_type'),
    )


class DecisionClaim(Base):
    """支持状态依据运行证据进行校验的报告主张。"""

    __tablename__ = 'decision_claims'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    decision_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey('decision_runs.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[str] = mapped_column(String(100), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    support_status: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_ref_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved_evidence_ref_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    agent_refs: Mapped[list] = mapped_column(PG_JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    decision_run: Mapped["DecisionRun"] = relationship(
        backref=backref('claims', cascade='all, delete-orphan', passive_deletes=True)
    )

    __table_args__ = (
        UniqueConstraint(
            'decision_run_id', 'claim_id', name='uq_decision_claims_run_claim'
        ),
        CheckConstraint(
            "claim_type IN ('fact', 'interpretation', 'recommendation', 'risk', 'uncertainty')",
            name='ck_decision_claims_claim_type',
        ),
        CheckConstraint(
            "support_status IN ('supported', 'partial', 'unsupported', 'conflicting')",
            name='ck_decision_claims_support_status',
        ),
        CheckConstraint(
            'confidence IS NULL OR (confidence >= 0 AND confidence <= 1)',
            name='ck_decision_claims_confidence',
        ),
        CheckConstraint(
            'evidence_ref_count >= 0 AND resolved_evidence_ref_count >= 0 '
            'AND resolved_evidence_ref_count <= evidence_ref_count',
            name='ck_decision_claims_evidence_ref_counts',
        ),
        Index('idx_decision_claims_run_status', 'decision_run_id', 'support_status'),
    )


class DecisionClaimEvidence(Base):
    """一条主张与一条证据记录之间已验证的关系。"""

    __tablename__ = 'decision_claim_evidence'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    decision_claim_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey('decision_claims.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    decision_evidence_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey('decision_evidences.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    relation: Mapped[str] = mapped_column(String(20), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    claim: Mapped["DecisionClaim"] = relationship(
        backref=backref('evidence_relations', cascade='all, delete-orphan', passive_deletes=True)
    )
    evidence: Mapped["DecisionEvidence"] = relationship(
        backref=backref('claim_relations', cascade='all, delete-orphan', passive_deletes=True)
    )

    __table_args__ = (
        UniqueConstraint(
            'decision_claim_id',
            'decision_evidence_id',
            'relation',
            name='uq_decision_claim_evidence_relation',
        ),
        CheckConstraint(
            "relation IN ('supports', 'contradicts', 'qualifies')",
            name='ck_decision_claim_evidence_relation',
        ),
        CheckConstraint('sequence >= 0', name='ck_decision_claim_evidence_sequence'),
    )


class DecisionEvidenceMetrics(Base):
    """单次决策运行的非内容性证据质量计数器。"""

    __tablename__ = 'decision_evidence_metrics'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    decision_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey('decision_runs.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
    )
    evidence_candidates_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_cited_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_refs_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_refs_resolved_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_ref_resolvable_ratio: Mapped[Optional[float]] = mapped_column(Float)
    supported_claim_ratio: Mapped[Optional[float]] = mapped_column(Float)
    unique_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snippet_only_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_context_dropped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    evidence_detail_load_failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    decision_run: Mapped["DecisionRun"] = relationship(
        backref=backref(
            'evidence_metrics',
            uselist=False,
            cascade='all, delete-orphan',
            passive_deletes=True,
        )
    )

    __table_args__ = (
        CheckConstraint(
            'evidence_candidates_total >= 0 AND evidence_cited_total >= 0 '
            'AND evidence_refs_total >= 0 AND evidence_refs_resolved_total >= 0 '
            'AND unique_source_count >= 0 AND snippet_only_count >= 0 '
            'AND evidence_context_dropped_count >= 0 '
            'AND evidence_detail_load_failure_count >= 0',
            name='ck_decision_evidence_metrics_nonnegative',
        ),
        CheckConstraint(
            'evidence_refs_resolved_total <= evidence_refs_total',
            name='ck_decision_evidence_metrics_refs_resolved',
        ),
        CheckConstraint(
            'evidence_ref_resolvable_ratio IS NULL OR '
            '(evidence_ref_resolvable_ratio >= 0 AND evidence_ref_resolvable_ratio <= 1)',
            name='ck_decision_evidence_metrics_ref_ratio',
        ),
        CheckConstraint(
            'supported_claim_ratio IS NULL OR '
            '(supported_claim_ratio >= 0 AND supported_claim_ratio <= 1)',
            name='ck_decision_evidence_metrics_claim_ratio',
        ),
    )

    def to_dict(self) -> dict:
        return {
            'evidence_candidates_total': self.evidence_candidates_total,
            'evidence_cited_total': self.evidence_cited_total,
            'evidence_ref_resolvable_ratio': self.evidence_ref_resolvable_ratio,
            'supported_claim_ratio': self.supported_claim_ratio,
            'unique_source_count': self.unique_source_count,
            'snippet_only_count': self.snippet_only_count,
            'evidence_context_dropped_count': self.evidence_context_dropped_count,
            'evidence_detail_load_failure_count': self.evidence_detail_load_failure_count,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }


# ==================== Integration 集成类 ====================

class IntegrationClient(Base):
    """可发起 AgentTeams 运行的已注册外部系统。

    ``client_key`` 是公开路由标识符；``credential_hash`` 是唯一持久化的凭据材料。
    客户端拥有自己的服务账户与功能开关，因此新增调用方无需在启动核心中复制 Agent Teams 专属分支。
    """
    __tablename__ = 'integration_clients'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    # 稳定的协议/工作流选择器。``client_key`` 标识调用方/租户；
    # 多个调用方可以有意共享同一个适配器。与迁移最终态一致：
    # NOT NULL 且无默认值，遗漏声明在写入时显式失败（fail-closed）。
    adapter_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    credential_hash: Mapped[Optional[str]] = mapped_column(String(128))
    # 密钥轮换期间，紧邻的上一个凭据仅在 ``previous_credential_expires_at``
    # 之前保持有效。两个哈希都不会通过 admin API 暴露。
    previous_credential_hash: Mapped[Optional[str]] = mapped_column(String(128))
    previous_credential_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    service_account_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    capabilities_json: Mapped[Optional[dict]] = mapped_column(PG_JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive
    )

    service_account: Mapped[Optional["User"]] = relationship(
        foreign_keys=[service_account_id]
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_key': self.client_key,
            'adapter_key': self.adapter_key,
            'display_name': self.display_name,
            'enabled': self.enabled,
            'capabilities': self.capabilities_json or {},
            'service_account_id': self.service_account_id,
            'has_previous_credential': bool(self.previous_credential_hash),
            'previous_credential_expires_at': (
                self.previous_credential_expires_at.isoformat() + 'Z'
                if self.previous_credential_expires_at else None
            ),
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }


# ==================== Agent Teams 兼容性存储 ====================

class AgentTeamsLaunch(Base):
    """Agent Teams 外部启动幂等记录"""
    __tablename__ = 'agent_teams_launches'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), default='agentteams', nullable=False)
    # 显式的本地归属与 ``source`` 各自独立：多个客户端
    # 租户可以共享同一个 Agent Teams 适配器和 source 命名空间。
    integration_client_key: Mapped[str] = mapped_column(
        String(50), default='agentteams', server_default='agentteams', nullable=False, index=True
    )
    # 存储宽度为外部契约上限（100）加 client 命名空间前缀预留。
    request_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_user_id: Mapped[Optional[str]] = mapped_column(String(100))
    source_patient_id: Mapped[Optional[str]] = mapped_column(String(100))
    source_conversation_id: Mapped[Optional[str]] = mapped_column(String(100))

    agentteams_conversation_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey('conversations.id'),
        index=True,
    )
    agentteams_leader_session_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey('leader_sessions.id'),
        index=True,
    )

    status: Mapped[str] = mapped_column(String(20), default='created', nullable=False, index=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100))
    lease_owner: Mapped[Optional[str]] = mapped_column(String(64))
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(PG_JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    conversation: Mapped[Optional["Conversation"]] = relationship(backref='agent_teams_launches')
    leader_session: Mapped[Optional["LeaderSession"]] = relationship(backref='agent_teams_launches')

    __table_args__ = (
        # 幂等键必须包含本地归属：多个客户端租户共享同一个
        # source 命名空间时，相同的外部 request-id 互不可见。
        UniqueConstraint(
            'source', 'integration_client_key', 'request_id',
            name='uq_agent_teams_launch_source_client_request',
        ),
        Index('idx_agent_teams_launch_source_conversation', 'source', 'source_conversation_id'),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'source': self.source,
            'integration_client_key': self.integration_client_key,
            'request_id': self.request_id,
            'source_user_id': self.source_user_id,
            'source_patient_id': self.source_patient_id,
            'source_conversation_id': self.source_conversation_id,
            'agentteams_conversation_id': self.agentteams_conversation_id,
            'agentteams_leader_session_id': self.agentteams_leader_session_id,
            'status': self.status,
            'error_code': self.error_code,
            'lease_owner': self.lease_owner,
            'lease_expires_at': self.lease_expires_at.isoformat() + 'Z' if self.lease_expires_at else None,
            'heartbeat_at': self.heartbeat_at.isoformat() + 'Z' if self.heartbeat_at else None,
            'attempt_count': self.attempt_count,
            'metadata': self.metadata_json or {},
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }


class AgentTeamsEmbedToken(Base):
    """Agent Teams 短期嵌入访问令牌"""
    __tablename__ = 'agent_teams_embed_tokens'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey('conversations.id'), nullable=False, index=True)
    leader_session_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('leader_sessions.id'), index=True)
    source: Mapped[str] = mapped_column(String(50), default='agentteams', nullable=False, index=True)
    integration_client_key: Mapped[str] = mapped_column(
        String(50), default='agentteams', server_default='agentteams', nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    conversation: Mapped["Conversation"] = relationship(backref='agent_teams_embed_tokens')
    leader_session: Mapped[Optional["LeaderSession"]] = relationship(backref='agent_teams_embed_tokens')

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'leader_session_id': self.leader_session_id,
            'source': self.source,
            'integration_client_key': self.integration_client_key,
            'expires_at': self.expires_at.isoformat() + 'Z' if self.expires_at else None,
            'revoked_at': self.revoked_at.isoformat() + 'Z' if self.revoked_at else None,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'last_used_at': self.last_used_at.isoformat() + 'Z' if self.last_used_at else None,
        }


# ==================== 集成访问操作 ====================

class IntegrationAccessOperation(Base):
    """访问治理操作的持久化本地状态。"""
    __tablename__ = 'integration_access_operations'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    client_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='requested')
    reason: Mapped[Optional[str]] = mapped_column(String(500))
    revoked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    remote_action: Mapped[str] = mapped_column(String(30), nullable=False, default='not_implemented', server_default='not_implemented')
    error_code: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (
        UniqueConstraint('client_key', 'action', 'operation_id', name='uq_integration_access_operation_scope'),
        Index('idx_integration_access_operation_client_created', 'client_key', 'created_at'),
    )

    def to_dict(self) -> dict:
        return {
            'operation_id': self.operation_id,
            'client_key': self.client_key,
            'action': self.action,
            'request_id': self.request_id,
            'status': self.status,
            'revoked_count': self.revoked_count,
            'remote_action': self.remote_action,
            'error_code': self.error_code,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }


# ==================== Leader 类 ====================

class LeaderSession(Base):
    """Leader Agent 会话表

    记录 Leader 工作流的状态和数据：

    状态管理（state）：
    - idle: 空闲
    - assessing: 需求评估中
    - questioning: 生成提问中
    - forming_team: 团队组建中
    - web_search: 网络搜索中
    - monitoring: 执行监控中
    - summarizing: 结果汇总中
    - completed: 已完成
    - stopped: 已停止
    - failed: 失败

    决策字段：
    - assessment_score: 需求复杂度评分（0-100）
    - risk_level: 风险等级（low/medium/high）
    - selected_agents: 选中的 Agent（逗号分隔）

    监控字段：
    - started_at: 开始时间
    - completed_at: 完成时间
    - total_tokens: Token 消耗
    - total_cost: 成本（精确数值）
    - stop_requested: 用户请求停止
    - error_message: 失败原因
    """
    __tablename__ = 'leader_sessions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey('conversations.id'), nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(String(10), default='zh-CN', nullable=False)

    # 状态管理
    state: Mapped[str] = mapped_column(String(20), default='idle')
    assessment_score: Mapped[Optional[int]] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(10), default='medium')  # low/medium/high

    # 团队信息
    selected_agents: Mapped[Optional[str]] = mapped_column(String(500))

    # 监控数据
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost: Mapped[float] = mapped_column(Numeric(10, 4), default=0.0)  # 4位小数

    # 停止标志
    stop_requested: Mapped[bool] = mapped_column(Boolean, default=False)

    # 失败原因
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # 需求循环计数（修复追问超限 bug）
    requirement_loop_count: Mapped[int] = mapped_column(Integer, default=0)

    # 工作流模板配置（由 WorkflowTemplate.apply 传入）
    assessment_threshold: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    system_prompt_addition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 关系
    messages: Mapped[List["Message"]] = relationship(
        backref='leader_session',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    tool_call_logs: Mapped[List["ToolCallLog"]] = relationship(
        lazy='dynamic',
        foreign_keys='ToolCallLog.leader_session_id',
        overlaps="leader_session"
    )

    # ==================== JSON 辅助方法 ====================

    def get_selected_agents_list(self) -> List[str]:
        """获取选中的 agents 列表"""
        if not self.selected_agents:
            return []
        return [agent.strip() for agent in self.selected_agents.split(',') if agent.strip()]

    def set_selected_agents_list(self, agents_list: List[str]) -> None:
        """设置选中的 agents 列表"""
        self.selected_agents = ','.join(agents_list) if agents_list else ''

    def get_assessment_details(self) -> dict:
        """
        从 Message 表获取评估详情

        Returns:
            dict: 评估详情，如果不存在返回空字典
        """
        from sqlalchemy.orm import Session
        message = Session.object_session(self).query(Message).filter_by(
            leader_session_id=self.id,
            message_type='assessment'
        ).first()

        if message and message.content:
            return message.content.get('details', {})
        return {}

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'user_message': self.user_message,
            'locale': self.locale,
            'state': self.state,
            'assessment_score': self.assessment_score,
            'risk_level': self.risk_level,
            'selected_agents': self.get_selected_agents_list(),
            'started_at': self.started_at.isoformat() + 'Z' if self.started_at else None,
            'completed_at': self.completed_at.isoformat() + 'Z' if self.completed_at else None,
            'total_tokens': self.total_tokens,
            'total_cost': float(self.total_cost) if self.total_cost else 0.0,
            'stop_requested': self.stop_requested,
            'error_message': self.error_message
        }


class LeaderWorkflowCancellation(Base):
    """Leader 工作流的跨 worker 持久化取消标记。

    该行刻意不设置指向 LeaderSession 或 Conversation 的外键，这样删除级联不会在
    另一个 worker 读取到取消信号之前将其抹除。
    """
    __tablename__ = 'leader_workflow_cancellations'

    session_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reason: Mapped[str] = mapped_column(String(100), default='user_requested', nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False, index=True
    )


# 字段验证事件监听器
@event.listens_for(LeaderSession, 'before_insert')
@event.listens_for(LeaderSession, 'before_update')
def validate_leader_session(mapper, connection, target):
    """
    验证 LeaderSession 字段

    状态验证：必须是有效状态之一
    评分验证：0-100 范围
    风险等级验证：low/medium/high
    """
    valid_states = [
        'idle', 'assessing', 'questioning', 'forming_team',
        'web_search', 'monitoring', 'summarizing',
        'completed', 'stopped', 'failed'
    ]

    valid_risk_levels = ['low', 'medium', 'high']

    # 验证 state
    if target.state is not None and target.state not in valid_states:
        raise ValueError(f"Invalid state '{target.state}'. Must be one of: {valid_states}")

    # 验证 assessment_score
    if target.assessment_score is not None:
        if not isinstance(target.assessment_score, (int, float)):
            raise ValueError(f"assessment_score must be a number")
        if not (0 <= target.assessment_score <= 100):
            raise ValueError(f"assessment_score must be between 0 and 100, got {target.assessment_score}")

    # 验证 risk_level
    if target.risk_level is not None and target.risk_level not in valid_risk_levels:
        raise ValueError(f"Invalid risk_level '{target.risk_level}'. Must be one of: {valid_risk_levels}")


class LeaderAgentResult(Base):
    """Leader Agent 执行结果表

    记录每个 Agent 的执行结果：

    基本信息：
    - agent_id: Agent 标识
    - agent_name: Agent 名称

    执行结果：
    - status: 状态（success/failed）
    - content: 回复内容
    - error: 错误信息

    统计数据：
    - tool_calls: 工具调用记录（JSON）
    - tokens_used: Token 使用量
    - execution_time: 执行时间（秒）
    - iterations: 迭代次数

    排序：
    - sequence_number: 执行顺序（唯一）
    """
    __tablename__ = 'leader_agent_results'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey('conversations.id'), nullable=False, index=True)
    leader_session_id: Mapped[int] = mapped_column(Integer, ForeignKey('leader_sessions.id', ondelete='CASCADE'), nullable=False, index=True)

    # Agent 基本信息
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # 执行结果
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success, failed
    content: Mapped[Optional[str]] = mapped_column(Text)
    content_locale: Mapped[str] = mapped_column(String(10), default='zh-CN', nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)

    # OpenHarness 整合字段
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSON)  # 工具调用记录
    decomposition: Mapped[Optional[dict]] = mapped_column(PG_JSONB)  # 子任务分解计划及执行结果
    summary: Mapped[Optional[dict]] = mapped_column(PG_JSONB)  # AgentReportSummary
    structured_report: Mapped[Optional[dict]] = mapped_column(PG_JSONB)  # StructuredAgentReport
    raw_tool_results: Mapped[Optional[dict]] = mapped_column(PG_JSONB)  # evidence_id 对应的原始工具结果
    evidence_map: Mapped[Optional[dict]] = mapped_column(PG_JSONB)  # list[ReportEvidence]
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    execution_time: Mapped[float] = mapped_column(Float, default=0.0)
    iterations: Mapped[int] = mapped_column(Integer, default=1)

    # 排序和时间戳
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    # 关系
    conversation: Mapped["Conversation"] = relationship(backref='leader_agent_results')
    leader_session: Mapped["LeaderSession"] = relationship(backref=backref('agent_results', cascade='all, delete-orphan'))

    # 验证器
    @validates('status')
    def validate_status(self, key, status):
        if status not in ['success', 'failed']:
            raise ValueError(f"Invalid status: {status}. Must be 'success' or 'failed'")
        return status

    @validates('sequence_number')
    def validate_sequence_number(self, key, seq):
        if seq < 1:
            raise ValueError(f"sequence_number must be >= 1, got {seq}")
        return seq

    # 表级约束
    __table_args__ = (
        UniqueConstraint('leader_session_id', 'sequence_number', name='unique_agent_result_sequence'),
        Index('idx_agent_result_conversation_created', 'conversation_id', 'created_at'),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'leader_session_id': self.leader_session_id,
            'agent_id': self.agent_id,
            'agent_name': self.agent_name,
            'status': self.status,
            'content': self.content,
            'content_locale': self.content_locale,
            'error': self.error,
            'tool_calls': self.tool_calls,
            'decomposition': self.decomposition,
            'summary': self.summary,
            'structured_report': self.structured_report,
            'raw_tool_results': self.raw_tool_results,
            'evidence_map': self.evidence_map,
            'tokens_used': self.tokens_used,
            'execution_time': self.execution_time,
            'iterations': self.iterations,
            'sequence_number': self.sequence_number,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None
        }

    def __repr__(self) -> str:
        return f'<LeaderAgentResult {self.agent_id}:{self.status}>'


class LeaderFinalReport(Base):
    """Leader 最终报告表

    存储 Leader 工作流的最终汇总报告：
    - report: Markdown 格式的完整报告

    关系：
    - leader_session_id: 唯一关联一个 Leader 会话
    """
    __tablename__ = 'leader_final_reports'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey('conversations.id'), nullable=False, index=True)
    leader_session_id: Mapped[int] = mapped_column(Integer, ForeignKey('leader_sessions.id', ondelete='CASCADE'), nullable=False, unique=True)

    # 报告内容
    report: Mapped[str] = mapped_column(Text, nullable=False)
    content_locale: Mapped[str] = mapped_column(String(10), default='zh-CN', nullable=False)
    executive_summary: Mapped[Optional[dict]] = mapped_column(PG_JSONB)
    structured_report: Mapped[Optional[dict]] = mapped_column(PG_JSONB)
    evidence_map: Mapped[Optional[dict]] = mapped_column(PG_JSONB)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    # 关系
    conversation: Mapped["Conversation"] = relationship(backref='leader_final_reports')
    leader_session: Mapped["LeaderSession"] = relationship(backref=backref('final_report', uselist=False, cascade='all, delete-orphan'))

    __table_args__ = (
        Index('idx_final_report_conversation_created', 'conversation_id', 'created_at'),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'leader_session_id': self.leader_session_id,
            'report': self.report,
            'content_locale': self.content_locale,
            'summary': self.executive_summary,
            'executive_summary': self.executive_summary,
            'structured_report': self.structured_report,
            'evidence_map': self.evidence_map,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None
        }

    def __repr__(self) -> str:
        return f'<LeaderFinalReport session={self.leader_session_id}>'


class LeaderReportRating(Base):
    """Leader 报告评分表

    用户对 Leader 产物（Agent 报告或最终报告）的评分与反馈：
    - target_type: agent_result | final_report
    - target_id: LeaderAgentResult.id 或 LeaderFinalReport.id
    - rating: 1 (差评) 或 5 (好评)
    - comment: 可选文字反馈

    约束：
    - (user_id, target_type, target_id) 唯一，覆盖更新
    - leader_session_id / conversation_id 冗余存储，便于权限校验与统计
    """
    __tablename__ = 'leader_report_ratings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # 评分目标
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)  # agent_result | final_report
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # 所属会话（冗余，用于权限校验）
    leader_session_id: Mapped[int] = mapped_column(Integer, ForeignKey('leader_sessions.id', ondelete='CASCADE'), nullable=False)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey('conversations.id'), nullable=False)

    # 评分用户
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)

    # 评分内容
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 or 5
    comment: Mapped[Optional[str]] = mapped_column(Text)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    # 关系
    user: Mapped["User"] = relationship(backref='leader_report_ratings')
    leader_session: Mapped["LeaderSession"] = relationship(backref='report_ratings')
    conversation: Mapped["Conversation"] = relationship(backref='leader_report_ratings')

    # 验证器
    @validates('target_type')
    def validate_target_type(self, key, target_type):
        if target_type not in ['agent_result', 'final_report']:
            raise ValueError(f"Invalid target_type: {target_type}. Must be 'agent_result' or 'final_report'")
        return target_type

    @validates('rating')
    def validate_rating(self, key, rating):
        if rating not in [1, 5]:
            raise ValueError(f"Invalid rating: {rating}. Must be 1 or 5")
        return rating

    # 表级约束
    __table_args__ = (
        UniqueConstraint('user_id', 'target_type', 'target_id', name='unique_user_target_rating'),
        Index('idx_rating_target', 'target_type', 'target_id'),
        Index('idx_rating_session', 'leader_session_id'),
        Index('idx_rating_conversation', 'conversation_id'),
        Index('idx_rating_created', 'created_at'),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'leader_session_id': self.leader_session_id,
            'conversation_id': self.conversation_id,
            'user_id': self.user_id,
            'rating': self.rating,
            'comment': self.comment,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None
        }

    def __repr__(self) -> str:
        return f'<LeaderReportRating {self.target_type}:{self.target_id} rating={self.rating}>'


class SecurityLog(Base):
    """安全日志表

    记录敏感操作审计：
    - 管理员登录
    - 用户封禁

    用于：
    - 安全审计
    - 异常检测
    - 追溯调查
    """
    __tablename__ = 'security_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('users.id'), index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50))
    resource_id: Mapped[Optional[int]] = mapped_column(Integer)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), index=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    details: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)

    # 关系
    user: Mapped[Optional["User"]] = relationship(backref='security_logs')

    __table_args__ = (
        Index('idx_security_log_user_created', 'user_id', 'created_at'),
        Index('idx_security_log_action', 'action'),
    )

    # 操作类型常量
    ACTION_ADMIN_LOGIN = 'admin_login'
    ACTION_USER_BAN = 'user_ban'

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'details': self.details,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None
        }

    def __repr__(self) -> str:
        return f'<SecurityLog action={self.action} user={self.user_id}>'


# ==================== OpenHarness 类 ====================

class HarnessSessionMapping(Base):
    """OpenHarness 会话映射表

    映射 Leader 会话到 OpenHarness Session：
    - leader_session_id: Leader 会话 ID
    - harness_session_id: OpenHarness Session ID
    - harness_metadata: 附加元数据（JSON）
    """
    __tablename__ = 'harness_session_mappings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    leader_session_id: Mapped[int] = mapped_column(Integer, ForeignKey('leader_sessions.id'), nullable=False, index=True)
    harness_session_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    harness_metadata: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    # 关系
    leader_session: Mapped["LeaderSession"] = relationship(backref=backref('harness_mappings', cascade='all, delete-orphan'))

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'leader_session_id': self.leader_session_id,
            'harness_session_id': self.harness_session_id,
            'harness_metadata': self.harness_metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self) -> str:
        return f'<HarnessSessionMapping leader={self.leader_session_id} harness={self.harness_session_id}>'


# ==================== Agent 权限类 ====================

class AgentMcpPermission(Base):
    """Agent MCP 工具权限配置表

    配置每个 Agent 可使用的 MCP 工具：
    - agent_id: Agent 标识
    - mcp_tool_pattern: 工具模式（支持通配符）
    - enabled: 是否启用

    通配符规则：
    - mcp__exa__* 匹配所有 exa 工具
    - mcp__playwright__browser_* 匹配 browser_ 开头的工具

    默认无配置 = 无 MCP 工具权限
    """
    __tablename__ = 'agent_mcp_permissions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    mcp_tool_pattern: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (
        UniqueConstraint('agent_id', 'mcp_tool_pattern', name='uq_agent_mcp_pattern'),
        Index('idx_agent_mcp_enabled', 'agent_id', 'enabled'),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'mcp_tool_pattern': self.mcp_tool_pattern,
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None
        }

    def __repr__(self) -> str:
        return f'<AgentMcpPermission agent={self.agent_id} pattern={self.mcp_tool_pattern}>'


class AgentPriorityRule(Base):
    """Agent 优先级规则配置表

    支持通过场景、风险、分类组合触发优先级调整：

    触发条件（null 或 '*' 匹配所有）：
    - trigger_scene: 场景（technology/medical/business）
    - trigger_risk_level: 风险等级（low/medium/high）
    - trigger_category: 分类（肿瘤/心血管/等）

    优先级调整：
    - agent_id: 目标 Agent
    - priority: 优先级值（0-100，小值先执行）
    - rule_priority: 规则优先级（冲突时大者优先）

    执行逻辑：
    - 相同 priority 的 Agent 并行执行
    - 不同 priority 按 priority 升序执行

    示例：
    - 医疗肿瘤场景：检验科=40, 放射科=45, 肿瘤内科=50
    - 检验先执行 → 放射次之 → 内科最后
    """
    __tablename__ = 'agent_priority_rules'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # 触发条件（null 匹配所有）
    trigger_scene: Mapped[Optional[str]] = mapped_column(String(50))
    trigger_risk_level: Mapped[Optional[str]] = mapped_column(String(10))
    trigger_category: Mapped[Optional[str]] = mapped_column(String(50))

    # 优先级调整
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    rule_priority: Mapped[int] = mapped_column(Integer, default=0)

    # 元数据
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (
        Index('idx_trigger_conditions', 'trigger_scene', 'trigger_risk_level', 'trigger_category'),
        Index('idx_agent_id', 'agent_id'),
        Index('idx_rule_priority_active', 'rule_priority', 'is_active'),
    )

    def matches(self, scene: str, risk_level: str, category: str) -> bool:
        """
        检查规则是否匹配给定条件

        通配符规则：
        - null 或 '*' 表示匹配所有值

        Args:
            scene: 场景类型
            risk_level: 风险等级
            category: 分类

        Returns:
            bool: 是否匹配且启用
        """
        if not self.is_active:
            return False

        # 场景匹配
        if self.trigger_scene and self.trigger_scene != '*' and self.trigger_scene != scene:
            return False

        # 风险等级匹配
        if self.trigger_risk_level and self.trigger_risk_level != '*' and self.trigger_risk_level != risk_level:
            return False

        # 分类匹配
        if self.trigger_category and self.trigger_category != '*' and self.trigger_category != category:
            return False

        return True

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'trigger_scene': self.trigger_scene,
            'trigger_risk_level': self.trigger_risk_level,
            'trigger_category': self.trigger_category,
            'agent_id': self.agent_id,
            'priority': self.priority,
            'rule_priority': self.rule_priority,
            'description': self.description,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None
        }

    def __repr__(self) -> str:
        return f'<AgentPriorityRule agent={self.agent_id} priority={self.priority}>'


# ==================== 知识库类 ====================

class KnowledgeDocument(Base):
    """知识库文档元数据表

    记录知识库文档的完整信息：

    基本信息：
    - filename: 文件名
    - original_path: 原始文件路径
    - markdown_path: OCR 输出的 Markdown 路径
    - category: 分类（regulation/workflow/contract/news）

    文件属性：
    - file_size: 文件大小
    - file_type: 类型（pdf/docx/md/txt）
    - content_hash: MD5 去重

    处理状态：
    - status: pending/processing/indexed/failed
    - ocr_processed_at: OCR 处理时间
    - ocr_error: OCR 错误
    - graphify_processed_at: graphify 处理时间
    - graphify_error: graphify 错误
    - graph_nodes/edges: 图谱统计
    """
    __tablename__ = 'knowledge_documents'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)  # 安全处理后的文件名
    original_filename: Mapped[Optional[str]] = mapped_column(String(500))  # 用户上传时的原始文件名
    original_path: Mapped[Optional[str]] = mapped_column(String(500))
    markdown_path: Mapped[Optional[str]] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(20), default='regulation')  # regulation|workflow|contract|news
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    file_type: Mapped[Optional[str]] = mapped_column(String(20))  # pdf|docx|md|txt
    content_hash: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    uploaded_by: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default='pending')  # pending|processing|indexed|failed
    ocr_error: Mapped[Optional[str]] = mapped_column(Text)
    ocr_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # graphify 提取字段
    graphify_error: Mapped[Optional[str]] = mapped_column(Text)
    graphify_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    graph_nodes: Mapped[Optional[int]] = mapped_column(Integer)
    graph_edges: Mapped[Optional[int]] = mapped_column(Integer)

    __table_args__ = (
        Index('idx_knowledge_category', 'category'),
        Index('idx_knowledge_status', 'status'),
        Index('idx_knowledge_uploaded_by', 'uploaded_by'),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'category': self.category,
            'file_size': self.file_size,
            'file_type': self.file_type,
            'content_hash': self.content_hash,
            'uploaded_by': self.uploaded_by,
            'uploaded_at': self.uploaded_at.isoformat() + 'Z',
            'indexed_at': self.indexed_at.isoformat() + 'Z' if self.indexed_at else None,
            'status': self.status,
            'ocr_error': self.ocr_error,
            'ocr_processed_at': self.ocr_processed_at.isoformat() + 'Z' if self.ocr_processed_at else None,
            'graphify_error': self.graphify_error,
            'graphify_processed_at': self.graphify_processed_at.isoformat() + 'Z' if self.graphify_processed_at else None,
            'graph_nodes': self.graph_nodes,
            'graph_edges': self.graph_edges,
        }

    def __repr__(self) -> str:
        return f'<KnowledgeDocument {self.filename} status={self.status}>'


class KnowledgeCategory(Base):
    """知识库分类配置表

    Admin 可管理分类列表：
    - key: 分类键（regulation/workflow/contract/news）
    - label: 中文标签（制度/流程/合同/新闻）
    - description: 分类描述
    - icon: Element Plus 图标名
    - sort_order: 排序顺序
    - is_active: 是否启用

    文档上传时从该表获取可用分类选项。
    """
    __tablename__ = 'knowledge_categories'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(200))
    icon: Mapped[str] = mapped_column(String(50), default='Document')
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('users.id'), nullable=True, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (
        Index('idx_knowledge_category_sort', 'sort_order'),
        Index('idx_knowledge_category_active', 'is_active'),
        Index('idx_knowledge_category_user', 'user_id'),
        UniqueConstraint('key', 'user_id', name='uq_knowledge_category_key_user'),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'key': self.key,
            'label': self.label,
            'description': self.description,
            'icon': self.icon,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() + 'Z',
            'updated_at': self.updated_at.isoformat() + 'Z'
        }

    def __repr__(self) -> str:
        return f'<KnowledgeCategory {self.key} label={self.label}>'


# ==================== Agent 组合包类 ====================

class AgentPack(Base):
    """Agent 组合包表

    将多个 Agent 组合成可复用的团队配置：
    - name: 组合包名称
    - description: 描述
    - category: 分类（medical/business/research/custom）
    - is_system: 系统预设 vs 用户自建
    - creator_id: 创建者（系统预设为 NULL）
    - agents: JSONB 数组，每项含 agent_id / role / order
    - tags: JSONB 标签
    - usage_count: 使用计数

    agents JSONB 示例：
    [
      {"agent_id": "心内科专家", "role": "主导分析", "order": 1},
      {"agent_id": "影像科专家", "role": "辅助诊断", "order": 2}
    ]
    """
    __tablename__ = 'agent_packs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_key: Mapped[str] = mapped_column(
        String(100), default=lambda: f'pack-{uuid4()}', nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), default='custom', nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creator_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    agents: Mapped[list] = mapped_column(PG_JSONB, default=list, nullable=False)
    tags: Mapped[Optional[list]] = mapped_column(PG_JSONB, default=list)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    # 关系
    creator: Mapped[Optional["User"]] = relationship(backref='agent_packs')

    __table_args__ = (
        UniqueConstraint('catalog_key', name='uq_agent_pack_catalog_key'),
        Index('idx_agent_pack_category_system', 'category', 'is_system'),
        Index('idx_agent_pack_creator', 'creator_id'),
        UniqueConstraint('name', 'creator_id', name='uq_agent_pack_name_creator'),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'is_system': self.is_system,
            'creator_id': self.creator_id,
            'agents': self.agents or [],
            'tags': self.tags or [],
            'usage_count': self.usage_count,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f'<AgentPack {self.name} system={self.is_system}>'


# ==================== 工作流模板类 ====================

class WorkflowTemplate(Base):
    """工作流模板表

    将常用 Leader 配置保存为可复用模板：
    - name: 模板名称
    - description: 描述
    - category: 分类（medical/business/research/custom）
    - is_system: 系统预设 vs 用户自建
    - creator_id: 创建者（系统预设为 NULL）

    Agent 组合（二选一，pack_id 优先）：
    - pack_id: 引用 AgentPack
    - agents: JSONB 直接定义的 Agent 列表

    工作流配置：
    - skip_assessment: 是否跳过评估（快速模式）
    - assessment_threshold: 评估通过阈值（0-100，默认 60）
    - system_prompt_addition: 注入到 Agent 的额外系统提示

    统计：
    - usage_count: 使用次数
    - last_used_at: 最后使用时间
    """
    __tablename__ = 'workflow_templates'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_key: Mapped[str] = mapped_column(
        String(100), default=lambda: f'template-{uuid4()}', nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), default='custom', nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creator_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    # Agent 组合（二选一，pack_id 优先）
    pack_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('agent_packs.id', ondelete='SET NULL'), nullable=True)
    agents: Mapped[Optional[list]] = mapped_column(PG_JSONB, nullable=True)

    # 工作流配置
    skip_assessment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assessment_threshold: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    system_prompt_addition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 统计
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    # 关系
    creator: Mapped[Optional["User"]] = relationship(backref='workflow_templates')
    pack: Mapped[Optional["AgentPack"]] = relationship(backref='workflow_templates')

    __table_args__ = (
        UniqueConstraint('catalog_key', name='uq_workflow_template_catalog_key'),
        Index('idx_workflow_template_category_system', 'category', 'is_system'),
        Index('idx_workflow_template_creator', 'creator_id'),
        UniqueConstraint('name', 'creator_id', name='uq_workflow_template_name_creator'),
    )

    def resolve_agents(self, db_session=None) -> list:
        """解析模板实际 Agent 列表。pack_id 优先，否则用 agents 字段。
        返回 [{agent_id, role, order, name}] 格式。
        """
        raw = []
        if self.pack_id and db_session is not None:
            pack = db_session.get(AgentPack, self.pack_id)
            if pack and pack.agents:
                raw = pack.agents
        if not raw and self.agents:
            raw = self.agents
        if not raw or db_session is None:
            return [{'agent_id': a.get('agent_id', ''), 'role': a.get('role', ''),
                     'order': a.get('order', i + 1), 'name': a.get('agent_id', '')}
                    for i, a in enumerate(raw)]

        # 从 DB 批量查中文名
        ids = [a.get('agent_id', '') for a in raw if a.get('agent_id')]
        name_map = {}
        if ids:
            rows = db_session.query(AgentConfig.agent_id, AgentConfig.name).filter(
                AgentConfig.agent_id.in_(ids)).all()
            name_map = {r[0]: r[1] for r in rows}

        return [
            {'agent_id': a.get('agent_id', ''), 'role': a.get('role', ''),
             'order': a.get('order', i + 1),
             'name': name_map.get(a.get('agent_id', ''), a.get('agent_id', ''))}
            for i, a in enumerate(raw)
        ]

    def to_dict(self, db_session=None) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'is_system': self.is_system,
            'creator_id': self.creator_id,
            'pack_id': self.pack_id,
            'agents': self.agents or [],
            'resolved_agents': self.resolve_agents(db_session),
            'skip_assessment': self.skip_assessment,
            'assessment_threshold': self.assessment_threshold,
            'system_prompt_addition': self.system_prompt_addition,
            'usage_count': self.usage_count,
            'last_used_at': self.last_used_at.isoformat() + 'Z' if self.last_used_at else None,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f'<WorkflowTemplate {self.name} system={self.is_system}>'


# ==================== 记忆类 ====================

class AgentMemory(Base):
    """用户长期记忆表

    跨对话持久化用户偏好、决策、事实和约束。
    所有查询必须带 user_id，不得跨用户召回。

    字段说明：
    - content: 记忆内容（一句话摘要）
    - metadata_: JSONB 元数据（type, source, agent_id, tags）
    - importance: 重要性评分 0.0-1.0
    - embedding: 预留 pgvector 向量，第一阶段不使用
    - source_conversation_id/message_id: 记忆来源追溯
    """
    __tablename__ = 'agent_memories'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column(PG_JSONB, default=dict)  # JSONB
    source_conversation_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('conversations.id'))
    source_message_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('messages.id'))
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    embedding: Mapped[Optional[str]] = mapped_column(Text)  # 预留 pgvector
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    # 关系
    user: Mapped["User"] = relationship(backref='agent_memories')

    __table_args__ = (
        Index('idx_memory_user_importance', 'user_id', postgresql_using='btree'),
        Index('idx_memory_user_created', 'user_id', 'created_at'),
        # GIN 索引通过 Alembic 迁移创建（JSONB GIN 需要显式操作符表）
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'content': self.content,
            'metadata': self.metadata_,
            'source_conversation_id': self.source_conversation_id,
            'source_message_id': self.source_message_id,
            'importance': self.importance,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f'<AgentMemory user={self.user_id} type={self.metadata_.get("type", "?")}>'


# ==================== 知识图谱向量索引 ====================

class NodeEmbedding(Base):
    """知识图谱节点向量表

    存储 graph.json 节点 label 的 embedding 向量，用于语义相似度查询。
    由 EmbeddingService 在 graphify 提取完成后自动填充。

    - user_id: 用户 ID（按用户隔离）
    - node_id: graph.json 中的节点 ID
    - label: 节点标签（冗余存储，避免查询时再读 graph.json）
    - embedding: pgvector 向量列（1024 维，bge-m3 默认）
    - graph_version: graph.json 版本标识（mtime hash），用于失效判断
    """
    __tablename__ = 'node_embeddings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    embedding = mapped_column(Vector(1024)) if Vector else mapped_column(Text)
    graph_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    __table_args__ = (
        UniqueConstraint('user_id', 'node_id', name='uq_node_embedding_user_node'),
        Index('idx_node_embedding_user', 'user_id'),
        # HNSW 向量索引通过 Alembic 迁移创建（需要 pgvector 扩展）
    )

    def __repr__(self) -> str:
        return f'<NodeEmbedding user={self.user_id} node={self.node_id}>'


# ==================== LLM 模型配置 ====================

class LLMModel(Base):
    """LLM 模型配置表

    存储系统可用的 LLM 模型信息，替代原 config/models.yaml 配置文件。
    每个模型有独立的 base_url 和 api_key，支持多提供商接入。

    - model_id: 模型标识符（如 'deepseek-v4-pro'），全局唯一
    - display_name: 前端展示名称
    - base_url / api_key: 独立的 API 端点和密钥
    - context_limit / max_output_tokens: token 规格
    - is_enabled / is_default: 启用状态和默认模型标记
    - last_test_*: 自动探活结果
    """
    __tablename__ = 'llm_models'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    context_limit: Mapped[int] = mapped_column(Integer, default=128000, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=32768, nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String(100))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_test_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_test_ok: Mapped[Optional[bool]] = mapped_column(Boolean)
    last_test_error: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    def mask_api_key(self) -> str:
        """返回脱敏的 api_key（如 'sk-****7a3b'）"""
        key = self.api_key or ''
        if len(key) <= 8:
            return '****'
        return f'{key[:3]}****{key[-4:]}'

    def to_dict(self, include_sensitive: bool = False) -> dict:
        result = {
            'id': self.id,
            'model_id': self.model_id,
            'display_name': self.display_name,
            'context_limit': self.context_limit,
            'max_output_tokens': self.max_output_tokens,
            'provider': self.provider,
            'is_enabled': self.is_enabled,
            'is_default': self.is_default,
            'sort_order': self.sort_order,
            'last_test_at': self.last_test_at.isoformat() + 'Z' if self.last_test_at else None,
            'last_test_ok': self.last_test_ok,
            'last_test_error': self.last_test_error,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }
        if include_sensitive:
            # admin 接口返回完整 base_url，用于编辑回显；若需展示掩码另加 base_url_masked 字段
            result['base_url'] = self.base_url
            result['api_key_masked'] = self.mask_api_key()
        return result

    def __repr__(self) -> str:
        return f'<LLMModel {self.model_id}>'


class BackfillTask(Base):
    """能力补全后台任务表

    持久化 backfill-capabilities 任务状态，支持多 worker 部署。
    - task_id: UUID 前 8 位
    - status: running / completed / failed
    - total / processed / updated / skipped: 进度计数
    """
    __tablename__ = 'backfill_tasks'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default='running', nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    def to_dict(self) -> dict:
        return {
            'task_id': self.task_id,
            'status': self.status,
            'total': self.total,
            'processed': self.processed,
            'updated': self.updated,
            'skipped': self.skipped,
            'error': self.error,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'completed_at': self.completed_at.isoformat() + 'Z' if self.completed_at else None,
        }

    def __repr__(self) -> str:
        return f'<BackfillTask {self.task_id} status={self.status}>'


# NOTE: NodeEmbedding.__repr__ 定义在 NodeEmbedding 类内部（line ~1936）

