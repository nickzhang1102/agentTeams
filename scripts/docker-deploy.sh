#!/bin/bash

# Claude Chat System - 生产环境部署脚本
#
# 使用方法:
#   chmod +x scripts/docker-deploy.sh
#   ./scripts/docker-deploy.sh

set -e

echo "========================================"
echo "Claude Chat System - 生产环境部署"
echo "========================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Docker 和 Docker Compose
check_requirements() {
    echo "🔍 检查系统要求..."

    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker 未安装${NC}"
        echo "请先安装 Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi

    if ! docker compose version &> /dev/null; then
        echo -e "${RED}❌ Docker Compose 未安装${NC}"
        echo "请先安装 Docker Compose: https://docs.docker.com/compose/install/"
        exit 1
    fi

    echo -e "${GREEN}✅ Docker 和 Docker Compose 已安装${NC}"
    echo ""
}

# 检查环境变量文件
check_env_files() {
    echo "🔍 检查环境变量文件..."

    if [ ! -f "backend/.env" ]; then
        echo -e "${YELLOW}⚠️  backend/.env 文件不存在${NC}"
        echo "正在创建 backend/.env..."
        cp backend/.env.example backend/.env
        echo -e "${GREEN}✅ 已创建 backend/.env${NC}"
        echo ""
        echo -e "${YELLOW}⚠️  请编辑 backend/.env 文件，设置以下必填项:${NC}"
        echo "  - SECRET_KEY"
        echo "  - JWT_SECRET_KEY"
        echo ""
        echo "编辑完成后，重新运行此脚本"
        exit 1
    fi

    # 检查必填项
    source backend/.env

    if [ -z "$SECRET_KEY" ] || [ ${#SECRET_KEY} -lt 32 ] || [[ "$SECRET_KEY" == your-secret-key-* ]] || [ "$SECRET_KEY" == "change-this-to-a-random-secret-key-in-production" ]; then
        echo -e "${RED}❌ 请在 backend/.env 中设置至少 32 字符的随机 SECRET_KEY${NC}"
        exit 1
    fi

    if [ -z "$JWT_SECRET_KEY" ] || [ ${#JWT_SECRET_KEY} -lt 32 ] || [[ "$JWT_SECRET_KEY" == your-jwt-secret-key-* ]] || [ "$JWT_SECRET_KEY" == "change-this-to-a-random-jwt-secret-key-in-production" ]; then
        echo -e "${RED}❌ 请在 backend/.env 中设置至少 32 字符的随机 JWT_SECRET_KEY${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ 环境变量文件检查通过${NC}"
    echo ""
}

# 创建必要的目录
create_directories() {
    echo "📁 创建必要的目录..."
    mkdir -p backend/data/files
    mkdir -p backend/data/workspace
    mkdir -p logs
    echo -e "${GREEN}✅ 目录创建完成${NC}"
    echo ""
}

# 停止现有服务
stop_services() {
    echo "🛑 停止现有服务..."
    docker compose down 2>/dev/null || true
    echo -e "${GREEN}✅ 现有服务已停止${NC}"
    echo ""
}

# 构建镜像
build_images() {
    echo "🏗️  构建 Docker 镜像..."
    docker compose build --no-cache
    echo -e "${GREEN}✅ 镜像构建完成${NC}"
    echo ""
}

# 启动服务
start_services() {
    echo "🚀 启动服务..."
    docker compose up -d

    echo ""
    echo "⏳ 等待服务启动..."
    sleep 10

    # 检查服务状态
    if docker compose ps | grep -q "Up"; then
        echo -e "${GREEN}✅ 服务启动成功${NC}"
    else
        echo -e "${RED}❌ 服务启动失败${NC}"
        echo "查看日志: docker compose logs"
        exit 1
    fi
    echo ""
}

# 初始化数据库
init_database() {
    echo "🗄️  初始化数据库..."

    # 等待 PostgreSQL 启动
    echo "等待 PostgreSQL 启动..."
    sleep 5

    # 执行 Alembic 迁移（幂等，已迁移则跳过）
    echo "正在执行数据库迁移..."
    docker compose exec backend alembic upgrade head
    echo -e "${GREEN}✅ 数据库迁移完成${NC}"
    echo ""
}

# 显示访问信息
show_info() {
    echo "========================================"
    echo -e "${GREEN}✅ 部署完成！${NC}"
    echo "========================================"
    echo ""
    echo "🌐 访问地址:"
    echo "  前端: http://localhost:8380"
    echo "  后端: http://localhost:5000/api"
    echo ""
    echo "👤 管理员账号:"
    echo "  用户名: admin"
    echo "  初始密码: 随机生成，见 docker compose logs backend 输出"
    echo "            或宿主机 backend/data/.admin_initial_password 文件"
    echo "           （仅本地开发 APP_ENV=development 时为 admin/admin123）"
    echo ""
    echo -e "${YELLOW}⚠️  请使用初始密码登录并尽快修改！${NC}"
    echo -e "${YELLOW}⚠️  首次使用前，请登录后台添加并启用 LLM 模型。${NC}"
    echo ""
    echo "📋 常用命令:"
    echo "  查看日志: docker compose logs -f"
    echo "  停止服务: docker compose down"
    echo "  重启服务: docker compose restart"
    echo "  备份数据: docker compose exec postgres pg_dump -U postgres agent_teams > backup.sql"
    echo ""
}

# 主流程
main() {
    check_requirements
    check_env_files
    create_directories
    stop_services
    build_images
    start_services
    init_database
    show_info
}

# 执行部署
main
