"""
创建默认管理员账户
用于 Docker 容器启动时初始化

密码来源优先级（对齐 OncoPath 项目机制）：
1. ADMIN_INITIAL_PASSWORD 环境变量（推荐，配置在 backend/.env），
   需满足项目密码策略（长度 ≥ PASSWORD_MIN_LENGTH，含字母和数字）；
2. 本地/内网开发环境（APP_ENV=development）默认账号 admin/admin123；
3. 未设置且非开发环境时按生产姿态随机生成，打印一次并落盘
   backend/data/.admin_initial_password。

注意：
- 以上密码仅在 admin 账号不存在（首次创建）时使用，已存在的账号不会被覆盖；
- 初始密码一律在数据库提交成功后才输出/落盘，避免日志中出现未生效的密码；
- 忘记密码或账户被锁定时，运行 reset_admin.py 从 ADMIN_INITIAL_PASSWORD 重置。
"""
import os
import secrets

from config import Config
from db import db
from models import User
from services.agentteams_integration_account import ensure_agentteams_service_account


def initial_password_file_path() -> str:
    """随机初始密码落盘文件路径（backend/data/.admin_initial_password）。"""
    return os.path.join(os.path.dirname(__file__), 'data', '.admin_initial_password')


def validate_admin_password(password: str):
    """校验管理员密码是否符合项目密码策略。

    Returns:
        合法返回 None；不合法返回错误描述字符串。
    """
    if not password or len(password) < Config.PASSWORD_MIN_LENGTH:
        return f"密码长度至少为{Config.PASSWORD_MIN_LENGTH}个字符"
    if Config.PASSWORD_REQUIRE_LETTER and not any(c.isalpha() for c in password):
        return "密码必须包含字母"
    if Config.PASSWORD_REQUIRE_DIGIT and not any(c.isdigit() for c in password):
        return "密码必须包含数字"
    return None


def resolve_initial_password():
    """从 ADMIN_INITIAL_PASSWORD 环境变量解析初始密码。

    Returns:
        设置了合法环境变量时返回处理后的密码；未设置（或全空白）返回 None，
        由调用方走默认口令/随机密码回退逻辑。

    Raises:
        RuntimeError: 环境变量已设置但不满足密码策略（fail-closed）。
    """
    raw = os.environ.get('ADMIN_INITIAL_PASSWORD', '').strip()
    if not raw:
        return None
    error = validate_admin_password(raw)
    if error:
        raise RuntimeError(f"ADMIN_INITIAL_PASSWORD 不合法: {error}")
    return raw


def _remove_stale_password_file():
    """删除遗留的随机初始密码文件（其内容已不再反映 admin 实际密码）。"""
    pw_file = initial_password_file_path()
    try:
        if os.path.exists(pw_file):
            os.remove(pw_file)
    except OSError:
        pass


def create_admin():
    """创建管理员账号：优先 ADMIN_INITIAL_PASSWORD，其次开发默认口令，否则随机生成"""
    try:
        env_password = resolve_initial_password()
        random_password = None
        is_dev = os.environ.get('APP_ENV') == 'development'

        admin = User.query.filter_by(username='admin').first()
        created = False
        if not admin:
            admin = User(
                username='admin',
                email='admin@example.com',
                is_admin=True
            )
            if env_password:
                # 推荐：密码来自环境变量，不在日志中泄露明文
                admin.set_password(env_password)
            elif is_dev:
                # 仅显式 APP_ENV=development 时使用默认口令
                # （fail-closed：未设置一律按生产随机密码处理）
                admin.set_password('admin123')
            else:
                random_password = secrets.token_urlsafe(16)
                admin.set_password(random_password)
            db.session.add(admin)
            created = True
        elif env_password:
            print('ℹ️  ADMIN_INITIAL_PASSWORD 已设置，但 admin 账号已存在，本次不修改。'
                  '如需重置密码请运行: python reset_admin.py')

        service_account = ensure_agentteams_service_account(db.session)

        # 提交成功后才输出任何密码相关信息，杜绝日志出现未生效的密码
        db.session.commit()

        print(f'✅ Agent Teams 服务账户已就绪: {service_account.username}')

        if created:
            if env_password:
                _remove_stale_password_file()
                print('✅ 管理员已创建: admin'
                      '（初始密码来自 ADMIN_INITIAL_PASSWORD 环境变量，未在日志中显示）')
            elif is_dev:
                print('✅ 默认管理员已创建: admin/admin123')
                print('⚠️  请首次登录后立即修改默认密码！')
            else:
                # 随机密码：先落盘（失败不影响已生效的登录），再在日志中显示一次
                try:
                    pw_file = initial_password_file_path()
                    with open(pw_file, 'w', encoding='utf-8') as f:
                        f.write(f'admin: {random_password}\n')
                    os.chmod(pw_file, 0o600)  # 收紧权限：初始密码文件仅属主可读写
                    print(f'✅ 管理员已创建: admin（初始密码见 {pw_file}）')
                except OSError:
                    print('✅ 管理员已创建: admin')
                print('=' * 60)
                print(f'初始密码（仅显示这一次，请立即保存并登录修改）: {random_password}')
                print('=' * 60)
        else:
            print('ℹ️  管理员账号已存在')
    except Exception as e:
        db.session.rollback()
        print(f'❌ 创建管理员失败: {e}')
        raise
    finally:
        db.session.remove()


if __name__ == '__main__':
    create_admin()
