# 集成客户端与会诊对账运维指南

这份指南面向维护 AgentTeams 外部集成的管理员和部署人员。它描述客户端凭证、通用 launch/status/reconcile/embed renew 接口，以及本地 embed access 撤销操作。

## 先记住三条边界

- `client_key` 标识调用方/租户，`adapter_key` 标识协议和工作流实现。多个客户端可以共享一个 adapter，但 request ID、launch、embed token 和撤销 operation 始终按客户端隔离。
- launch 先在本地提交会话和幂等记录，再尝试调度后台 workflow。提交后调度失败不会返回可诱导重复提交的 500；恢复监控会按持久化 launch 和 lease 接管。
- 本地 embed access 撤销只标记指定客户端和 request ID 下的短期 token 为 revoked。它不删除 Conversation、LeaderSession、Message 或审计记录，不调用远端删除，也不证明远端未创建。

## 通用集成接口

所有通用接口都使用客户端的集成密钥通过 `X-Integration-Key` 认证。launch 还必须带外部调用方生成的稳定 `X-Request-Id`；相同客户端、相同 request ID 的重放只能回到原 launch。

```text
POST /api/integrations/v1/{client_key}/consultation-launches
GET  /api/integrations/v1/{client_key}/consultation-launches/{request_id}
POST /api/integrations/v1/{client_key}/consultation-launches/{request_id}/reconcile
POST /api/integrations/v1/{client_key}/embed-sessions/renew
```

launch 请求使用 provider-neutral 字段：`user_ref`、`subject_ref`、`conversation_ref`、`title`、`message`、`locale` 和 `metadata`。status/reconcile 是只读查询，不创建会话、不调度 workflow；renew 只为已经定位到的 client-owned launch 换发访问令牌。

常见结果：

| 场景 | 结果 |
| --- | --- |
| 未知 client、错误密钥、禁用 client | 认证/集成错误；不会进入 adapter |
| 未注册 adapter | `501`，不会创建 Conversation |
| 同 request ID 且 payload 一致 | 返回既有 launch；不会重复创建会话 |
| request ID 对应的调度器暂时不可用 | launch 已提交并正常返回；恢复监控稍后接管 |
| status/reconcile 找不到记录 | `status=not_found`；不会猜测性重发 launch |

## 客户端生命周期

管理接口均位于 `/api/admin/integration-clients`，只允许管理员调用。

| 操作 | 端点 | 关键规则 |
| --- | --- | --- |
| 列表/详情 | `GET /`、`GET /{client_key}` | 只返回元数据，不返回任何密钥哈希或明文 |
| 创建 | `POST /` | 要求安全 service account；明文 `ik_...` 只在响应中展示一次 |
| 启用/禁用 | `PUT /{client_key}/enabled` | 禁用立即阻断新认证和既有 embed token 解析；重新启用仍会校验 service account |
| 轮换密钥 | `POST /{client_key}/rotate-key` | 新密钥只展示一次；旧密钥只在配置的重叠窗口内有效，窗口最长 7 天 |
| 生命周期审计 | `GET /{client_key}/audit` | 只读、按 client 过滤；审计中不写密钥或医疗正文 |

service account 必须满足：`account_type=service`、`login_disabled=true`、`is_admin=false`。普通用户账号、可网页登录的服务账号或管理员账号都必须 fail-closed。

### 密钥轮换步骤

1. 管理员调用 `rotate-key`，设置足够短但能完成发布的 `rotation_window_seconds`，保存响应中的新明文密钥。
2. 更新调用方配置并优先使用新密钥；在重叠窗口内用 status 请求验证新密钥和 client 归属。
3. 确认调用方已切换后，若需要立即使旧密钥失效，再次轮换并将窗口设为 `0`。系统不会在列表、详情或审计中恢复旧密钥。
4. 通过 `GET /{client_key}/audit` 核对 create/rotate/enable/disable 操作；不要把密钥写入工单、日志或 shell 历史。

## 本地 embed access 撤销

撤销前必须在外部系统确认处置依据，并填写可审计理由。操作定位使用调用方看到的原始 `request_id`，管理员不需要拼接共享 adapter 的内部 client 前缀。

```text
POST /api/admin/integration-clients/{client_key}/embed-tokens/revoke
Body: {
  "request_id": "<external request id>",
  "reason": "<non-blank operator reason>",
  "operation_id": "<optional stable local operation id>"
}

GET /api/admin/integration-clients/{client_key}/embed-tokens/revoke
    ?status=completed&limit=100
GET /api/admin/integration-clients/{client_key}/embed-tokens/revoke/{operation_id}
```

省略 `operation_id` 时系统按 `client_key + request_id` 派生稳定的本地 operation ID。重复提交同一个 operation 会返回第一次完成的结果，不会新增撤销或审计动作；跨 client 的 request ID 返回未找到。响应中的 `remote_action=not_implemented` 必须保留原义，不能解读为远端已删除、已匿名化或已退款。

## 本地数据盘点

管理员可以读取某个 client 的 PHI-safe 本地盘点：

```text
GET /api/admin/integration-clients/{client_key}/data-inventory
```

响应只返回按 client 精确归属的数量和治理元数据，不返回标题、消息、患者引用、会话正文、撤销理由、token 或其他业务 payload。每个分类会标明 `source`、`owner.client_key`、内容分类、保留依据以及当前动作边界，覆盖 launch、Conversation、Message、LeaderSession、embed token、本地治理 operation 和安全审计记录。

`contains_phi_content` 是保守的存在性指示，不是匿名化或删除证明；`content_classification` 也不代表已配置具体保留天数。当前本地/远端删除、匿名化和保留周期均显式为 `not_implemented`，`manual_review_required=true`。盘点是只读操作，不撤销访问、不调度工作流，也不会跨 client 回退查询。

## 部署后验证

在目标环境执行以下检查；当前开发机没有 Docker 时，只能完成静态契约和 Python 测试，不能把结果写成真实容器验收。

```bash
docker compose config
docker compose build backend
docker compose up -d postgres backend frontend
curl -fsS http://127.0.0.1:5000/health
docker compose exec backend python -m alembic heads
docker compose logs --tail=200 backend
```

验证 launch 恢复时，使用一次有效 request ID：

1. 调用通用 launch，确认返回会话和 embed 信息。
2. 在提交后让 scheduler 暂时不可用，确认接口仍返回已持久化结果而不是 500。
3. 用同一 request ID 重放，确认 Conversation 和 launch 数量不增加。
4. 恢复 scheduler，确认 recovery monitor 通过 lease 接管；status/reconcile 只能查询，不能触发第二次 launch。

迁移失败必须阻止后端继续启动；看到 migration error 时先修复数据库版本链，不要手工跳过 `alembic upgrade head`。

## 不在本指南范围内

远端 AgentTeams 的删除、匿名化和 PHI 保留周期尚未由本地集成契约定义。没有产品/合规确认前，不要通过数据库删除、重复 launch 或自定义远端请求来“补救”。
