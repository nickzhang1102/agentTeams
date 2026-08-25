"""
PostgreSQL 数据库初始化脚本

功能：
1. 创建文件存储目录
2. 创建所有数据表
3. 创建默认管理员账号

注意：
- 确保 PostgreSQL 服务已启动
- 确保 .env 文件中已配置 DATABASE_URL
- 确保数据库 agent_teams 已创建
"""

import os
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from models import User


def check_database_connection():
    """检查数据库连接"""
    try:
        # 尝试执行简单查询
        db.session.execute(db.text('SELECT 1'))
        return True
    except Exception as e:
        print(f'❌ 数据库连接失败: {e}')
        return False


def create_required_directories():
    """创建必要的目录"""
    basedir = os.path.abspath(os.path.dirname(__file__))
    data_dir = os.path.join(basedir, 'data')

    # 确保文件存储目录存在
    files_dir = os.path.join(data_dir, 'files')
    os.makedirs(files_dir, exist_ok=True)

    # 确保工作目录存在
    workspace_dir = os.path.join(data_dir, 'workspace')
    os.makedirs(workspace_dir, exist_ok=True)

    print(f'✅ 数据目录已创建: {data_dir}')
    print(f'   - 文件存储: {files_dir}')
    print(f'   - 工作目录: {workspace_dir}')


def init_database():
    """初始化 PostgreSQL 数据库"""
    print('=' * 60)
    print('PostgreSQL 数据库初始化')
    print('=' * 60)

    # 创建必要的目录
    create_required_directories()
    print()

    # 创建应用
    print('📦 初始化数据库...')
    app = create_app()

    with app.app_context():
        # 检查数据库连接
        print('🔌 检查数据库连接...')
        if not check_database_connection():
            print()
            print('❌ 无法连接到 PostgreSQL 数据库！')
            print()
            print('请确保：')
            print('1. PostgreSQL 服务已启动')
            print('2. 数据库 agent_teams 已创建')
            print('3. .env 文件中 DATABASE_URL 配置正确')
            print()
            print('创建数据库命令（Linux/Mac）：')
            print('  sudo -u postgres psql -c "CREATE DATABASE agent_teams;"')
            print()
            print('创建数据库命令（Windows）：')
            print('  psql -U postgres -c "CREATE DATABASE agent_teams;"')
            sys.exit(1)

        print('✅ 数据库连接成功')
        print()

        # 创建所有表
        print('🏗️  创建数据表...')
        try:
            db.create_all()
            print('✅ 数据表创建成功')
        except Exception as e:
            print(f'❌ 创建数据表失败: {e}')
            sys.exit(1)

        print()

        # 创建默认管理员账号
        print('👤 创建默认管理员账号...')
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            try:
                admin = User(
                    username='admin',
                    email='admin@example.com',
                    is_admin=True
                )
                # 使用 PBKDF2-SHA256 算法加密存储密码
                # werkzeug.security.generate_password_hash 会自动：
                # 1. 生成随机盐值（salt）
                # 2. 使用 PBKDF2 + SHA256 进行 260,000 次迭代哈希
                # 3. 存储格式: pbkdf2:sha256:260000$salt$hash
                # 密码在数据库中不是明文存储，无法逆向破解
                admin.set_password('admin123')  # ✅ 加密存储

                db.session.add(admin)
                db.session.commit()

                print('✅ 默认管理员账号已创建:')
                print('   用户名: admin')
                print('   密码: admin123')
                print()
                print('⚠️  请首次登录后立即修改默认密码！')
            except Exception as e:
                db.session.rollback()
                print(f'❌ 创建管理员账号失败: {e}')
                sys.exit(1)
        else:
            print('ℹ️  管理员账号已存在，跳过创建')

        print()
        print('=' * 60)
        print('✅ 数据库初始化完成！')
        print('=' * 60)
        print()
        print('下一步：')
        print('  启动后端服务: python run.py')
        print()


if __name__ == '__main__':
    init_database()
