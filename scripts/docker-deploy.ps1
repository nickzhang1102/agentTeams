# Claude Chat System - Windows PowerShell 部署脚本
#
# 使用方法:
#   .\scripts\docker-deploy.ps1

# 颜色函数
function Write-Success { param($text) Write-Host $text -ForegroundColor Green }
function Write-Error { param($text) Write-Host $text -ForegroundColor Red }
function Write-Warning { param($text) Write-Host $text -ForegroundColor Yellow }

Write-Host "========================================"
Write-Host "Claude Chat System - 生产环境部署"
Write-Host "========================================"
Write-Host ""

# 检查 Docker 和 Docker Compose
function Check-Requirements {
    Write-Host "🔍 检查系统要求..."

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "❌ Docker 未安装"
        Write-Host "请先安装 Docker Desktop: https://www.docker.com/products/docker-desktop"
        exit 1
    }

    docker compose version 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "❌ Docker Compose 未安装"
        Write-Host "Docker Desktop 通常已包含 Docker Compose V2"
        exit 1
    }

    Write-Success "✅ Docker 和 Docker Compose 已安装"
    Write-Host ""
}

# 检查环境变量文件
function Check-EnvFiles {
    Write-Host "🔍 检查环境变量文件..."

    if (-not (Test-Path "backend\.env")) {
        Write-Warning "⚠️  backend\.env 文件不存在"
        Write-Host "正在创建 backend\.env..."
        Copy-Item "backend\.env.example" "backend\.env"
        Write-Success "✅ 已创建 backend\.env"
        Write-Host ""
        Write-Warning "⚠️  请编辑 backend\.env 文件，设置以下必填项:"
        Write-Host "  - SECRET_KEY"
        Write-Host "  - JWT_SECRET_KEY"
        Write-Host ""
        Write-Host "编辑完成后，重新运行此脚本"
        exit 1
    }

    # 加载环境变量
    $envContent = Get-Content "backend\.env" | Where-Object { $_ -match "^([^#][^=]+)=(.*)$" }
    foreach ($line in $envContent) {
        $parts = $line -split "=", 2
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }

    $secretKey = [Environment]::GetEnvironmentVariable("SECRET_KEY", "Process")
    $jwtSecret = [Environment]::GetEnvironmentVariable("JWT_SECRET_KEY", "Process")

    if ([string]::IsNullOrEmpty($secretKey) -or $secretKey.Length -lt 32 -or $secretKey -like "your-secret-key-*" -or $secretKey -eq "change-this-to-a-random-secret-key-in-production") {
        Write-Error "❌ 请在 backend\.env 中设置至少 32 字符的随机 SECRET_KEY"
        exit 1
    }

    if ([string]::IsNullOrEmpty($jwtSecret) -or $jwtSecret.Length -lt 32 -or $jwtSecret -like "your-jwt-secret-key-*" -or $jwtSecret -eq "change-this-to-a-random-jwt-secret-key-in-production") {
        Write-Error "❌ 请在 backend\.env 中设置至少 32 字符的随机 JWT_SECRET_KEY"
        exit 1
    }

    Write-Success "✅ 环境变量文件检查通过"
    Write-Host ""
}

# 创建必要的目录
function Create-Directories {
    Write-Host "📁 创建必要的目录..."
    New-Item -ItemType Directory -Force -Path "backend\data\files" | Out-Null
    New-Item -ItemType Directory -Force -Path "backend\data\workspace" | Out-Null
    New-Item -ItemType Directory -Force -Path "logs" | Out-Null
    Write-Success "✅ 目录创建完成"
    Write-Host ""
}

# 停止现有服务
function Stop-Services {
    Write-Host "🛑 停止现有服务..."
    docker compose down 2>$null
    Write-Success "✅ 现有服务已停止"
    Write-Host ""
}

# 构建镜像
function Build-Images {
    Write-Host "🏗️  构建 Docker 镜像..."
    docker compose build --no-cache
    if ($LASTEXITCODE -ne 0) {
        Write-Error "❌ 镜像构建失败"
        exit 1
    }
    Write-Success "✅ 镜像构建完成"
    Write-Host ""
}

# 启动服务
function Start-Services {
    Write-Host "🚀 启动服务..."
    docker compose up -d
    if ($LASTEXITCODE -ne 0) {
        Write-Error "❌ 服务启动失败"
        exit 1
    }

    Write-Host ""
    Write-Host "⏳ 等待服务启动..."
    Start-Sleep -Seconds 10

    # 检查服务状态
    $status = docker compose ps
    if ($status -match "Up") {
        Write-Success "✅ 服务启动成功"
    } else {
        Write-Error "❌ 服务启动失败"
        Write-Host "查看日志: docker compose logs"
        exit 1
    }
    Write-Host ""
}

# 初始化数据库
function Init-Database {
    Write-Host "🗄️  初始化数据库..."

    # 等待 PostgreSQL 启动
    Write-Host "等待 PostgreSQL 启动..."
    Start-Sleep -Seconds 5

    # 执行 Alembic 迁移（幂等，已迁移则跳过）
    Write-Host "正在执行数据库迁移..."
    docker compose exec backend alembic upgrade head
    if ($LASTEXITCODE -eq 0) {
        Write-Success "✅ 数据库初始化完成"
    } else {
        Write-Warning "⚠️  数据库可能已初始化"
    }
    Write-Host ""
}

# 显示访问信息
function Show-Info {
    Write-Host "========================================"
    Write-Success "✅ 部署完成！"
    Write-Host "========================================"
    Write-Host ""
    Write-Host "🌐 访问地址:"
    Write-Host "  前端: http://localhost:8380"
    Write-Host "  后端: http://localhost:5000/api"
    Write-Host ""
    Write-Host "👤 管理员账号:"
    Write-Host "  用户名: admin"
    Write-Host "  初始密码: 随机生成，见 docker compose logs backend 输出"
    Write-Host "            或宿主机 backend/data/.admin_initial_password 文件"
    Write-Host "           （仅本地开发 APP_ENV=development 时为 admin/admin123）"
    Write-Host ""
    Write-Warning "⚠️  请使用初始密码登录并尽快修改！"
    Write-Warning "⚠️  首次使用前，请登录后台添加并启用 LLM 模型。"
    Write-Host ""
    Write-Host "📋 常用命令:"
    Write-Host "  查看日志: docker compose logs -f"
    Write-Host "  停止服务: docker compose down"
    Write-Host "  重启服务: docker compose restart"
    Write-Host "  备份数据: docker compose exec postgres pg_dump -U postgres agent_teams > backup.sql"
    Write-Host ""
}

# 主流程
Check-Requirements
Check-EnvFiles
Create-Directories
Stop-Services
Build-Images
Start-Services
Init-Database
Show-Info
