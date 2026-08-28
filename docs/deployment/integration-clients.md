# 集成客户端与会诊对账运维指南

这份指南面向维护 AgentTeams 外部集成的管理员和部署人员。它描述客户端凭证、通用 launch/status/reconcile 接口，以及本地 embed access 撤销操作。

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
```

launch 请求使用 provider-neutral 字段：`user_ref`、`subject_ref`、`conversation_ref`、`title`、`message`、`locale` 和 `metadata`。status/reconcile 是只读查询，不创建会话、不调度 workflow。嵌入令牌只在 launch 时签发，到期后需重新发起会诊。

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

## 集成协议契约 v1（调用方契约）

本节是与通用集成接口配套的 **v1 协议契约**，供外部调用方（如 OncoPath）实现。契约的运行时单一事实源是 capabilities 端点；调用方应先探测它，再按宣告值消费。

### 端点

```text
GET  /api/integrations/v1/{client_key}/capabilities                       # 版本/能力/限额/词表宣告
POST /api/integrations/v1/{client_key}/consultation-launches              # 启动（幂等）
GET  /api/integrations/v1/{client_key}/consultation-launches/{request_id} # 对账（只读）
POST /api/integrations/v1/{client_key}/consultation-launches/{request_id}/reconcile # 对账（只读）
POST /api/integrations/v1/{client_key}/consultation-launches/{request_id}/embed-token # 重签嵌入令牌（客户端鉴权；只铸造令牌，不创建/不调度）
```

### 请求头

| 头 | 必填 | 说明 |
| --- | --- | --- |
| `X-Integration-Key` | 是 | 集成密钥（两端共享的明文，本端 sha256 哈希存储） |
| `X-Request-Id` | 启动必填 | 调用方稳定的幂等键，≤100 字符 |
| `X-Integration-Protocol-Version` | 否 | 调用方声明协议版本，默认 1；超出支持范围返回 426 `unsupported_version` |

版本握手：声明版本高于当前部署或低于最低支持版本时，返回 `426 unsupported_version`；非整数声明返回 `400 invalid_payload`。未声明视为当前版本（向后兼容）。

### 启动载荷（provider-neutral）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_ref` | string≤100 | 调用方用户引用 |
| `subject_ref` | string≤100 | 调用方主体引用（OncoPath 为 patient_id） |
| `conversation_ref` | string≤100 | 调用方会诊引用（必填） |
| `title` | string≤500 | 会诊标题 |
| `message` | string 1..100000 | 会诊材料正文（必填） |
| `locale` | `zh-CN` / `en-US` | 语言 |
| `metadata` | object≤20000（序列化） | 调用方自定义元数据 |

### 响应信封（中立字段 + 遗留字段双发）

外部调用方应优先读取顶层**中立字段**；`agentteams_*` 遗留字段在过渡期保留、标记废弃：

| 中立字段 | 说明 |
| --- | --- |
| `request_id` | 调用方 request id（status 响应） |
| `status` | 规范状态 |
| `embed_path` | 嵌入路径（前端拼 base_url 使用） |
| `remote_conversation_id` / `remote_session_id` | provider 无关的远端会话标识 |
| `conversation_ref` / `subject_ref` / `user_ref` | 回显调用方引用 |
| `metadata` | provider 明细（`provider`、`embed_token`、`run_id`、`agentteams_*`） |

### 规范状态集

`created | running | completed | failed | stopped`；查询响应附加 `not_found`（找不到记录，不代表启动未发生，调用方不得据此重发启动）。

### 错误码（detail.error）

| 错误码 | HTTP | 语义 |
| --- | --- | --- |
| `invalid_integration_key` | 401 | 密钥缺失/不匹配 |
| `invalid_client` | 400 | client_key 缺失/非法 |
| `invalid_payload` | 400 | 载荷违反契约（字段超长、message 缺失等） |
| `integration_client_not_found` | 404 | client_key 未注册 |
| `integration_capability_disabled` | 403 | 客户端未开启该能力 |
| `integration_disabled` | 403 | 集成/客户端被禁用 |
| `service_account_not_configured` | 403 | 服务账户未配置或不安全 |
| `integration_adapter_unavailable` | 501 | 适配器未注册 |
| `idempotency_conflict` | 409 | 相同 request id 载荷不一致 |
| `unsupported_version` | 426 | 协议版本不兼容 |
| `invalid_embed_token` / `embed_session_not_found` | 401/404 | 嵌入访问错误 |
| `agentteams_launch_not_found` | 404 | 重签嵌入令牌时启动记录不存在 |
| `agentteams_launch_failed` / `agentteams_launch_stopped` | 409 | 重签嵌入令牌时启动已失败/已停止 |

调用方不应猜测本表之外的错误码；对未登记码应记录原始码并按 HTTP 语义分类（4xx 配置/载荷、5xx 不可用），不得回显远端 message 到终端用户。

### 历史会诊重签

嵌入令牌会过期（TTL 默认 3600s，可配 `AGENTTEAMS_EMBED_TOKEN_TTL_SECONDS`，下限 60s）并被同一会话的新令牌吊销，宿主重新打开历史会诊时不能用旧令牌。宿主可通过 `POST .../consultation-launches/{request_id}/embed-token`（客户端鉴权）为既有启动**重签**一个新令牌：只铸造令牌，不新建会话、不调度也不重启工作流，无额外汇计费副作用。重签定位启动记录时与 status 查询共享相同的客户端租户隔离（其它租户或遗留密钥一律 404 `agentteams_launch_not_found`）；启动已 `failed`/`stopped` 时返回 409。

表中 `invalid_client`（400）与 `integration_client_not_found`（404）指向"该部署未注册此 client_key"的部署状态类问题：调用方可按自身产品语义归类展示（例如映射为 503"集成暂不可用"），但日志中必须保留原始错误码，保证排障可追溯。

### 限额（capabilities.limits 宣告为准）

`message_max_length=100000`、`metadata_max_length=20000`（序列化）、`request_id_max_length=100`、`title_max_length=500`、`ref_max_length=100`、`min_message_length=1`。调用方发送前应预校验，避免超限请求换取 400。

### 兼容策略

- capabilities/版本握手/中立信封为叠加变更；未升级的调用方保持可用。
- `agentteams_*` 遗留响应字段与遗留 `/api/integrations/agentteams/*` 路由仅用于过渡，契约 v2 移除。
- 错误码 `unsupported_version` 由版本握手产生；`service_account_quota_exceeded` 已随计费下线删除，不再使用。

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
