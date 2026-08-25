#!/bin/bash
# 容器启动脚本：迁移 → 种子 → 服务
# 由 backend/Dockerfile COPY 进镜像（勿在此文件中使用 Windows CRLF 行尾）
set -e

echo "Running migrations..."
alembic upgrade head

echo "Creating admin..."
python init_admin.py

echo "Seeding agent configs..."
python seed_admin_data.py || echo "Warning: seed_admin_data failed, continuing startup"

echo "Seeding agent packs..."
python seed_agent_packs.py || echo "Warning: seed_agent_packs failed, continuing startup"

echo "Seeding workflow templates..."
python seed_workflow_templates.py || echo "Warning: seed_workflow_templates failed, continuing startup"

echo "Pre-generating RSA keys..."
# 多 worker 并发首请求会在密钥不存在时各自生成，产生竞态；启动前单进程生成一次
python - <<'EOF'
import os
from config import Config, generate_rsa_key_pair

keys_dir = Config.RSA_KEYS_DIR or 'keys'
private_path = os.path.join(keys_dir, 'private_key.pem')
public_path = os.path.join(keys_dir, 'public_key.pem')
if os.path.exists(private_path) and os.path.exists(public_path):
    print(f"RSA keys already exist at {keys_dir}")
else:
    os.makedirs(keys_dir, exist_ok=True)
    private_pem, public_pem = generate_rsa_key_pair()
    with open(private_path, 'w', encoding='utf-8') as f:
        f.write(private_pem)
    with open(public_path, 'w', encoding='utf-8') as f:
        f.write(public_pem)
    os.chmod(private_path, 0o600)
    os.chmod(public_path, 0o644)
    print(f"RSA keys generated at {keys_dir}")
EOF

echo "Starting uvicorn..."
exec gunicorn app:app -k uvicorn.workers.UvicornWorker -c gunicorn.conf.py
