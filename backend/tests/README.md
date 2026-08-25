# 后端测试运行说明

## 前置条件

1. **PostgreSQL 18 必须处于运行状态**（本机服务或 Docker 均可）。

2. **创建专用测试库**（测试会清空目标库全部表，绝不使用主库）：

   ```sql
   CREATE DATABASE agent_teams_test;
   ```

3. **配置测试库连接**：在 `backend/.env` 中设置 `TEST_DATABASE_URL`（详见 `.env.example` 注释）：

   ```
   TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agent_teams_test
   ```

## 运行

```bash
cd backend && pytest tests/ -v
```

## 注意事项：必须串行运行

所有测试共用同一个 `agent_teams_test` 库，**并发运行 pytest（如 `-n` 参数或多终端同时跑）会互删表，造成大面积假失败**。请始终单进程串行执行。
