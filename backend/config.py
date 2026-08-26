import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


def generate_rsa_key_pair():
    """生成 RSA 密钥对"""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # 导出私钥 (PEM 格式)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # 导出公钥 (PEM 格式)
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return private_pem.decode('utf-8'), public_pem.decode('utf-8')


class Config:
    # FastAPI 配置
    APP_TITLE = "Agent Teams API"
    APP_VERSION = "1.1.0"
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173')

    # 反向代理信任开关：仅当应用部署在可信反代（nginx 等）之后时开启，
    # 限流才会按 X-Forwarded-For 最左 IP 计数；直连部署必须保持 false，
    # 否则客户端可伪造该头绕过限流
    TRUST_PROXY = os.environ.get('TRUST_PROXY', 'false').lower() == 'true'

    # 安全配置：强制要求环境变量，不提供默认值
    SECRET_KEY = os.environ.get('SECRET_KEY')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')

    # 密码策略
    PASSWORD_MIN_LENGTH = int(os.environ.get('PASSWORD_MIN_LENGTH', '8'))
    PASSWORD_REQUIRE_LETTER = os.environ.get('PASSWORD_REQUIRE_LETTER', 'true').lower() == 'true'
    PASSWORD_REQUIRE_DIGIT = os.environ.get('PASSWORD_REQUIRE_DIGIT', 'true').lower() == 'true'

    # JWT Token配置 - 24小时过期
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)

    # 验证安全配置
    if not SECRET_KEY:
        raise ValueError(
            "SECRET_KEY 环境变量未设置！\n"
            "请在 .env 文件中配置：\n"
            "SECRET_KEY=your-secret-key-at-least-32-characters-long"
        )

    if not JWT_SECRET_KEY:
        raise ValueError(
            "JWT_SECRET_KEY 环境变量未设置！\n"
            "请在 .env 文件中配置：\n"
            "JWT_SECRET_KEY=your-jwt-secret-key-at-least-32-characters-long"
        )

    # 密钥强度校验：长度不足 32 字符视为弱密钥，拒绝启动
    if len(SECRET_KEY) < 32:
        raise ValueError(
            "SECRET_KEY 强度不足！长度需 ≥ 32 字符（当前 "
            f"{len(SECRET_KEY)} 字符）。\n"
            "建议使用：python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    if len(JWT_SECRET_KEY) < 32:
        raise ValueError(
            "JWT_SECRET_KEY 强度不足！长度需 ≥ 32 字符（当前 "
            f"{len(JWT_SECRET_KEY)} 字符）。\n"
            "建议使用：python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    # 占位值黑名单：.env.example 的示例串满足长度校验，
    # 若原样用于部署，JWT 将以 GitHub 公开字符串签名
    for _name, _value in (('SECRET_KEY', SECRET_KEY), ('JWT_SECRET_KEY', JWT_SECRET_KEY)):
        if _value.startswith('your-') or 'change-in-production' in _value:
            raise ValueError(
                f"{_name} 仍为示例占位值，拒绝启动！\n"
                "请生成真实密钥并写入 .env：\n"
                "python -c \"import secrets; print(secrets.token_hex(32))\""
            )

    # Embedding 向量服务配置（用于 GraphRAG 语义搜索）
    # Embedding 是独立服务，不回退到后台管理的生成式 LLM 凭证。
    EMBEDDING_BASE_URL = os.environ.get('EMBEDDING_BASE_URL')
    EMBEDDING_API_KEY = os.environ.get('EMBEDDING_API_KEY', '')
    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'bge-m3')

    # 知识库数据根目录（文档存储、图谱提取输出、用户级图谱 JSON 等）
    # 用户级图谱路径通过 get_user_graph_path(user_id) 动态生成
    KNOWLEDGE_DATA_DIR = os.environ.get('KNOWLEDGE_DATA_DIR') or \
        os.path.join(basedir, '..', 'data', 'knowledge')

    @staticmethod
    def get_user_graph_path(user_id: int) -> str:
        """用户图谱 JSON 路径: data/knowledge/user_{id}_graph.json"""
        return os.path.join(Config.KNOWLEDGE_DATA_DIR, f'user_{user_id}_graph.json')

    # 数据库配置
    # 必须设置 DATABASE_URL 环境变量
    # 格式: postgresql://用户名:密码@主机:端口/数据库名
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 测试数据库 URL（与生产库隔离，防止测试误删生产数据）
    TEST_DATABASE_URL = os.environ.get('TEST_DATABASE_URL')

    # 验证数据库配置
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError(
            "DATABASE_URL 环境变量未设置！\n"
            "请在 .env 文件中配置数据库连接：\n"
            "DATABASE_URL=postgresql://用户名:密码@主机:端口/数据库名"
        )

    # 文件存储路径
    FILE_STORAGE_PATH = os.environ.get('FILE_STORAGE_PATH') or \
        os.path.join(basedir, 'data', 'files')

    # Agents目录
    AGENTS_DIR = os.environ.get('AGENTS_DIR') or \
        os.path.join(basedir, '..', '.claude', 'agents')

    # 工作目录（临时）
    WORKSPACE_DIR = os.environ.get('WORKSPACE_DIR') or \
        os.path.join(basedir, 'data', 'workspace')

    # SSE 连接超时配置
    LEADER_SSE_MAX_DURATION = int(os.environ.get('LEADER_SSE_MAX_DURATION', '3600'))  # Leader SSE 最大时长（秒），默认 60 分钟
    STALE_SESSION_TIMEOUT_MINUTES = int(os.environ.get('STALE_SESSION_TIMEOUT_MINUTES', '30'))  # 残留会话清理阈值（分钟）
    STALE_SESSION_GRACE_SECONDS = int(os.environ.get('STALE_SESSION_GRACE_SECONDS', '300'))
    AGENTTEAMS_LAUNCH_LEASE_SECONDS = int(os.environ.get('AGENTTEAMS_LAUNCH_LEASE_SECONDS', '120'))
    AGENTTEAMS_LAUNCH_HEARTBEAT_SECONDS = int(os.environ.get('AGENTTEAMS_LAUNCH_HEARTBEAT_SECONDS', '30'))
    AGENTTEAMS_EMBED_FRAME_ANCESTORS = os.environ.get('AGENTTEAMS_EMBED_FRAME_ANCESTORS', "'self'")

    # OpenHarness 整合配置
    OPENHARNESS_VERSION = '0.1.9'
    OPENHARNESS_ENABLED = os.environ.get('OPENHARNESS_ENABLED', 'true').lower() == 'true'
    OPENHARNESS_TOOLS_ENABLED = os.environ.get('OPENHARNESS_TOOLS_ENABLED', 'true').lower() == 'true'
    # shell 类工具（bash/edit_file）默认不分配给任何 Agent；显式开启后才进入技术类白名单。
    # 这类工具与后端服务同用户运行、不具备容器级隔离，默认关闭以缩小
    # LLM 可控内容驱动宿主命令执行的暴露面（见 SECURITY.md「工具执行边界」）。
    OPENHARNESS_SHELL_TOOLS_ENABLED = os.environ.get('OPENHARNESS_SHELL_TOOLS_ENABLED', 'false').lower() == 'true'
    OPENHARNESS_WORKSPACE = WORKSPACE_DIR  # 向后兼容别名（废弃，请使用 WORKSPACE_DIR）
    OPENHARNESS_TOOLS_TIMEOUT = int(os.environ.get('OPENHARNESS_TOOLS_TIMEOUT', '300'))

    # OpenHarness 协调器配置
    OPENHARNESS_COORDINATOR_ENABLED = os.environ.get('OPENHARNESS_COORDINATOR_ENABLED', 'true').lower() == 'true'
    MAX_AGENT_ITERATIONS = int(os.environ.get('MAX_AGENT_ITERATIONS', '10'))
    MAX_AGENT_PARALLEL = int(os.environ.get('MAX_AGENT_PARALLEL', '5'))

    # OpenHarness 原生环境变量（后台管理可配置）
    OPENHARNESS_MAX_TOKENS = int(os.environ.get('OPENHARNESS_MAX_TOKENS', '16384'))
    OPENHARNESS_TIMEOUT = float(os.environ.get('OPENHARNESS_TIMEOUT', '30.0'))
    OPENHARNESS_CONFIG_DIR = os.environ.get('OPENHARNESS_CONFIG_DIR', '')

    # Phase 4: 记忆与治理配置
    OPENHARNESS_MEMORY_ENABLED = os.environ.get('OPENHARNESS_MEMORY_ENABLED', 'true').lower() == 'true'
    OPENHARNESS_MEMORY_MAX_MESSAGES = int(os.environ.get('OPENHARNESS_MEMORY_MAX_MESSAGES', '50'))  # 记忆压缩阈值
    OPENHARNESS_PERMISSION_ENABLED = os.environ.get('OPENHARNESS_PERMISSION_ENABLED', 'true').lower() == 'true'
    OPENHARNESS_HOOKS_ENABLED = os.environ.get('OPENHARNESS_HOOKS_ENABLED', 'true').lower() == 'true'
    OPENHARNESS_HOOKS_TIMEOUT = int(os.environ.get('OPENHARNESS_HOOKS_TIMEOUT', '10'))  # 钩子执行超时（秒）

    # RSA 密钥配置
    RSA_KEYS_DIR = os.environ.get('RSA_KEYS_DIR') or \
        os.path.join(basedir, 'keys')  # RSA 密钥存储目录


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    # SECRET_KEY/JWT_SECRET_KEY 继承父类（父类导入时已强制校验环境变量）
    # 测试环境使用临时 Agent 目录
    AGENTS_DIR = os.path.join(basedir, 'tests', 'test_agents')
    # 测试环境工作目录
    WORKSPACE_DIR = os.path.join(basedir, 'tests', 'test_workspace')
    OPENHARNESS_WORKSPACE = WORKSPACE_DIR  # 向后兼容别名
    OPENHARNESS_ENABLED = True
    OPENHARNESS_TOOLS_ENABLED = True
    OPENHARNESS_TOOLS_TIMEOUT = 60


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    # 安全默认：未识别的环境一律按生产处理（fail-closed）
    'default': ProductionConfig
}
