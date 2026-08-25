-- Agent Teams 数据库初始化 SQL
-- 此脚本在 PostgreSQL 容器首次启动时自动执行

-- 设置客户端编码
SET client_encoding = 'UTF8';

-- 创建扩展（如果需要）
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 数据库由 POSTGRES_USER 创建；向当前初始化用户确认权限，兼容自定义用户名
GRANT ALL PRIVILEGES ON DATABASE agent_teams TO CURRENT_USER;

-- 输出成功消息
\echo 'PostgreSQL 数据库初始化完成'
