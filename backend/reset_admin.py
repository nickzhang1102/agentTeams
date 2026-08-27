#!/usr/bin/env python3
"""重置 admin 管理员密码（对齐 OncoPath 项目的 reset_admin 机制）

从 ADMIN_INITIAL_PASSWORD 环境变量读取新密码，然后：
- 重置 admin 账号密码（需满足项目密码策略）
- 清除登录失败计数与账户锁定状态（忘密被锁时可直接解锁）
- 清理遗留的随机初始密码落盘文件 backend/data/.admin_initial_password

只影响 admin 账号本身，不改动其他用户与数据。

用法：
- Docker 部署（一次性传入环境变量，无需重启容器）:
    docker compose exec -e ADMIN_INITIAL_PASSWORD='NewPass123' backend python reset_admin.py
- 本地开发：先在 backend/.env 设置 ADMIN_INITIAL_PASSWORD，再运行:
    python reset_admin.py

注意：admin 账号不存在时本脚本不会创建它，请先正常启动一次后端，
由 init_admin.py 在首次启动时使用同一环境变量创建。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import SessionLocal
from init_admin import initial_password_file_path, validate_admin_password
from models import User


def main() -> int:
    password = os.environ.get('ADMIN_INITIAL_PASSWORD', '').strip()
    if not password:
        print('❌ 未设置 ADMIN_INITIAL_PASSWORD 环境变量，无法确定重置后的密码。')
        print("   示例: docker compose exec -e ADMIN_INITIAL_PASSWORD='NewPass123' "
              'backend python reset_admin.py')
        return 1
    error = validate_admin_password(password)
    if error:
        print(f'❌ ADMIN_INITIAL_PASSWORD 不合法: {error}')
        return 1

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(username='admin').first()
        if not user:
            print('❌ admin 用户不存在：请先正常启动一次后端（init_admin.py 会创建它），再执行重置。')
            return 1

        print('=' * 60)
        print(f'即将重置管理员账号: {user.username} (id={user.id})')
        if user.locked_until:
            print('检测到账户处于锁定状态，将一并清除锁定。')
        print('=' * 60)

        user.set_password(password)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.lockout_reason = None
        session.commit()

        # 遗留的随机初始密码文件已失效，防止今后误读旧密码
        try:
            pw_file = initial_password_file_path()
            if os.path.exists(pw_file):
                os.remove(pw_file)
                print(f'[OK] 已清理过期初始密码文件: {pw_file}')
        except OSError as e:
            print(f'[WARN] 初始密码文件清理失败（不影响重置结果）: {e}')

        print('[OK] admin 密码已重置为 ADMIN_INITIAL_PASSWORD 的值（不在输出中显示明文）')
        print('[OK] 登录失败计数与锁定状态已清零')
        return 0
    except Exception as e:
        session.rollback()
        print(f'❌ 重置失败: {e}')
        return 1
    finally:
        session.close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n\n操作已取消')
        sys.exit(130)
