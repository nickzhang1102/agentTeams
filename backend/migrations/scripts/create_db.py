"""
创建 PostgreSQL 数据库脚本
"""
import os
import psycopg
from psycopg import sql
from urllib.parse import urlparse
from dotenv import load_dotenv


def create_database():
    """创建 agent_teams 数据库"""

    # 加载环境变量
    load_dotenv()

    # 从 DATABASE_URL 解析连接信息
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ 错误: 未找到 DATABASE_URL 环境变量")
        print("\n请在 .env 文件中配置数据库连接：")
        print("DATABASE_URL=postgresql://用户名:密码@主机:端口/数据库名")
        print("\n示例：")
        print("DATABASE_URL=postgresql://postgres:your_password@localhost:5432/agent_teams")
        return

    # 解析数据库连接 URL
    parsed = urlparse(database_url)

    # 提取连接参数
    host = parsed.hostname or 'localhost'
    port = parsed.port or 5432
    user = parsed.username
    password = parsed.password
    dbname = parsed.path.lstrip('/')  # 目标数据库名

    if not user or not password:
        print("❌ 错误: DATABASE_URL 中缺少用户名或密码")
        print("\n正确的格式：")
        print("DATABASE_URL=postgresql://用户名:密码@主机:端口/数据库名")
        return

    print(f"正在连接到 PostgreSQL 服务器 ({host}:{port})...")

    try:
        # 连接到默认数据库 postgres
        conn = psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname='postgres'  # 连接到默认数据库
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # 检查数据库是否已存在
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (dbname,)
        )
        exists = cursor.fetchone()

        if exists:
            print(f"数据库 {dbname} 已存在")
        else:
            # 创建数据库
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(dbname)
                )
            )
            print(f"数据库 {dbname} 创建成功")

        cursor.close()
        conn.close()

    except psycopg.OperationalError as e:
        print(f"连接失败: {e}")
        print("请检查 PostgreSQL 服务是否启动，以及连接参数是否正确")
    except Exception as e:
        print(f"创建数据库时出错: {e}")


if __name__ == "__main__":
    create_database()
