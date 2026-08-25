"""
创建默认管理员账户
用于 Docker 容器启动时初始化

本地/内网开发环境（APP_ENV=development）默认账号 admin/admin123；
其他环境（如 production）自动生成随机密码并仅在首次创建时打印一次，
避免使用公开已知的默认口令。
"""
import os
import secrets

from db import db
from models import User
from services.agentteams_integration_account import ensure_agentteams_service_account


def create_admin():
    """创建管理员账号：开发环境用固定默认口令，生产环境随机生成"""
    try:
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@example.com',
                is_admin=True
            )
            # 仅显式 APP_ENV=development 时使用默认口令（fail-closed：未设置一律按生产随机密码处理）
            is_dev = os.environ.get('APP_ENV') == 'development'
            if is_dev:
                admin.set_password('admin123')
                print('✅ 默认管理员已创建: admin/admin123')
                print('⚠️  请首次登录后立即修改默认密码！')
            else:
                random_password = secrets.token_urlsafe(16)
                admin.set_password(random_password)
                # 同时落盘到挂载卷，防止容器日志滚动后无法找回初始密码
                try:
                    pw_file = os.path.join(os.path.dirname(__file__), 'data', '.admin_initial_password')
                    os.makedirs(os.path.dirname(pw_file), exist_ok=True)
                    with open(pw_file, 'w', encoding='utf-8') as f:
                        f.write(f'admin: {random_password}\n')
                    # 收紧权限：初始密码文件仅属主可读写
                    os.chmod(pw_file, 0o600)
                    print(f'✅ 管理员已创建: admin（初始密码见 {pw_file}）')
                except OSError:
                    print('✅ 管理员已创建: admin')
                print('=' * 60)
                print(f'初始密码（仅显示这一次，请立即保存并登录修改）: {random_password}')
                print('=' * 60)
        else:
            print('ℹ️  管理员账号已存在')

        service_account = ensure_agentteams_service_account(db.session)
        db.session.commit()
        print(f'✅ Agent Teams 服务账户已就绪: {service_account.username}')
    except Exception as e:
        db.session.rollback()
        print(f'❌ 创建管理员失败: {e}')
        raise
    finally:
        db.session.remove()


if __name__ == '__main__':
    create_admin()
