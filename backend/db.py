"""
数据库基础设施模块

使用原生 SQLAlchemy 2.0：
- DeclarativeBase 声明式基类
- SessionLocal 会话工厂
- Engine 连接池配置
- scoped_session 包装（兼容 db.session 接口）
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session, scoped_session

from config import Config


# ==================== Engine 配置 ====================

# 创建 SQLAlchemy engine
engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,      # 连接健康检查
    pool_recycle=3600,       # 连接回收时间（秒）
    pool_size=5,             # 连接池大小（4 workers × 15 = 60，留余量给 PG 默认 100）
    max_overflow=10,         # 最大溢出连接
    pool_timeout=10,         # 获取连接超时（秒），快速失败避免级联
    echo=False,              # 生产环境关闭 SQL 日志
)

# ==================== 会话工厂 ====================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)

# 创建 scoped_session，线程安全
# 提供 db.session 接口，兼容 legacy 服务层代码
SessionScoped = scoped_session(SessionLocal)


# ==================== DBWrapper（前置定义） ====================

class DBWrapper:
    """
    数据库操作包装器

    提供 db.session 接口，兼容 legacy 服务层代码：
    - db.session.add()
    - db.session.commit()
    - db.session.rollback()
    - db.session.query()
    - db.session.flush()

    使用 scoped_session 实现，线程安全。

    测试兼容方法：
    - db.create_all()
    - db.drop_all()
    """

    @property
    def session(self) -> Session:
        """获取当前线程的数据库会话"""
        return SessionScoped

    def add(self, instance):
        """添加对象到会话"""
        self.session.add(instance)

    def commit(self):
        """提交会话"""
        self.session.commit()

    def rollback(self):
        """回滚会话"""
        self.session.rollback()

    def flush(self):
        """刷新会话（不提交）"""
        self.session.flush()

    def begin_nested(self):
        """创建 SAVEPOINT，与原生 SQLAlchemy Session 接口保持一致。"""
        return self.session.begin_nested()

    def query(self, *entities, **kwargs):
        """创建查询对象"""
        return self.session.query(*entities, **kwargs)

    def get(self, entity, ident, **kwargs):
        """根据主键获取对象

        透传 with_for_update / populate_existing 等 SQLAlchemy 2.0
        Session.get 支持的关键字参数，保持与原生 Session 接口一致。
        """
        return self.session.get(entity, ident, **kwargs)

    def delete(self, instance):
        """删除对象"""
        self.session.delete(instance)

    def close(self):
        """关闭会话"""
        self.session.close()

    def remove(self):
        """移除当前线程的会话"""
        SessionScoped.remove()

    def refresh(self, instance):
        """刷新对象状态（从数据库重新加载）"""
        self.session.refresh(instance)

    def create_all(self):
        """创建所有表（测试兼容）"""
        Base.metadata.create_all(bind=engine)

    def drop_all(self):
        """删除所有表（测试兼容，使用 CASCADE 处理外键依赖）

        安全守卫：拒绝在非测试数据库上执行。
        仅当数据库名包含 'test' 或使用 SQLite 时允许。
        """
        db_url = str(engine.url)
        db_name = engine.url.database or ''
        is_sqlite = db_url.startswith('sqlite')
        is_test_db = 'test' in db_name.lower()

        if not is_sqlite and not is_test_db:
            raise RuntimeError(
                f"拒绝在非测试数据库 '{db_name}' 上执行 drop_all()！"
                f"仅允许测试数据库（名称含 'test'）或 SQLite。"
                f"如需重置生产库，请手动执行 SQL。"
            )

        # 直接用 raw SQL CASCADE 删除所有表，避免 metadata.drop_all 的外键依赖问题
        with engine.connect() as conn:
            # 获取所有表名
            result = conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ))
            tables = [row[0] for row in result]
            if tables:
                # CASCADE 删除所有表（包括遗留表）
                conn.execute(text(f"DROP TABLE IF EXISTS {', '.join(tables)} CASCADE"))
                conn.commit()


# 全局 db 对象，提供 db.session 接口
db = DBWrapper()


# ==================== 声明式基类 ====================

class Base(DeclarativeBase):
    """
    所有数据库模型的声明式基类

    使用 SQLAlchemy 2.0 的 DeclarativeBase：
    - 支持 Mapped[] 类型注解
    - 支持 mapped_column() 列定义

    测试兼容：提供 query 类属性，返回 db.query(Model)
    """

    @classmethod
    @property
    def query(cls):
        """返回查询对象（测试兼容）"""
        return db.query(cls)


# ==================== 辅助函数 ====================

def get_db_session() -> Session:
    """
    获取数据库会话

    用于非 FastAPI 上下文（如后台任务、脚本）。
    FastAPI 路由应使用 Depends(get_db)。

    注意：调用者需负责关闭会话。
    """
    return SessionLocal()
