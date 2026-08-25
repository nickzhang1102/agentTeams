-- Leader 表重构手动迁移脚本
-- 执行时间：当数据库连接正常时
-- 用途：手动创建新表并迁移数据

-- ============================================================
-- 步骤 1: 创建 leader_agent_results 表
-- ============================================================
CREATE TABLE IF NOT EXISTS leader_agent_results (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    leader_session_id INTEGER NOT NULL REFERENCES leader_sessions(id) ON DELETE CASCADE,
    agent_id VARCHAR(50) NOT NULL,
    agent_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    content TEXT,
    error TEXT,
    sequence_number INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_agent_result_conversation
ON leader_agent_results(conversation_id);

CREATE INDEX IF NOT EXISTS idx_agent_result_session
ON leader_agent_results(leader_session_id);

CREATE INDEX IF NOT EXISTS idx_agent_result_agent
ON leader_agent_results(agent_id);

CREATE INDEX IF NOT EXISTS idx_agent_result_conversation_created
ON leader_agent_results(conversation_id, created_at);

-- 添加唯一约束
ALTER TABLE leader_agent_results
ADD CONSTRAINT unique_agent_result_sequence
UNIQUE (leader_session_id, sequence_number);

-- ============================================================
-- 步骤 2: 创建 leader_final_reports 表
-- ============================================================
CREATE TABLE IF NOT EXISTS leader_final_reports (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    leader_session_id INTEGER NOT NULL REFERENCES leader_sessions(id) ON DELETE CASCADE,
    report TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_final_report_conversation
ON leader_final_reports(conversation_id);

CREATE INDEX IF NOT EXISTS idx_final_report_conversation_created
ON leader_final_reports(conversation_id, created_at);

-- 添加唯一约束
ALTER TABLE leader_final_reports
ADD CONSTRAINT unique_final_report_session
UNIQUE (leader_session_id);

-- ============================================================
-- 步骤 3: 迁移 agent_result 数据
-- ============================================================
-- 注意：这里使用 INSERT ... SELECT 从 leader_messages 迁移数据
-- 需要根据实际数据结构调整

INSERT INTO leader_agent_results (
    conversation_id,
    leader_session_id,
    agent_id,
    agent_name,
    status,
    content,
    error,
    sequence_number,
    created_at
)
SELECT
    conversation_id,
    leader_session_id,
    content->>'agent_id' AS agent_id,
    content->>'agent_name' AS agent_name,
    content->>'status' AS status,
    content->>'content' AS content,
    content->>'error' AS error,
    sequence_number,
    created_at
FROM leader_messages
WHERE message_type = 'agent_result'
  AND content->>'agent_id' IS NOT NULL
  AND content->>'agent_name' IS NOT NULL
  AND content->>'status' IN ('success', 'failed');

-- ============================================================
-- 步骤 4: 迁移 final_report 和 summary 数据
-- ============================================================
INSERT INTO leader_final_reports (
    conversation_id,
    leader_session_id,
    report,
    created_at
)
SELECT
    conversation_id,
    leader_session_id,
    COALESCE(
        content->>'report',
        content->>'text'
    ) AS report,
    created_at
FROM leader_messages
WHERE message_type IN ('final_report', 'summary')
  AND COALESCE(content->>'report', content->>'text') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM leader_final_reports
      WHERE leader_final_reports.leader_session_id = leader_messages.leader_session_id
  );

-- ============================================================
-- 步骤 5: 验证迁移结果
-- ============================================================
-- 检查迁移的数据条数
SELECT
    'leader_messages (agent_result)' AS table_name,
    COUNT(*) AS count
FROM leader_messages
WHERE message_type = 'agent_result'
UNION ALL
SELECT
    'leader_agent_results' AS table_name,
    COUNT(*) AS count
FROM leader_agent_results
UNION ALL
SELECT
    'leader_messages (final_report/summary)' AS table_name,
    COUNT(*) AS count
FROM leader_messages
WHERE message_type IN ('final_report', 'summary')
UNION ALL
SELECT
    'leader_final_reports' AS table_name,
    COUNT(*) AS count
FROM leader_final_reports;

-- ============================================================
-- 步骤 6: 清理已迁移的旧数据（可选，谨慎执行）
-- ============================================================
-- 如果确认迁移成功，可以删除已迁移的 leader_messages 记录
-- 建议先备份数据！

-- DELETE FROM leader_messages
-- WHERE message_type = 'agent_result'
--   AND EXISTS (
--       SELECT 1 FROM leader_agent_results
--       WHERE leader_agent_results.leader_session_id = leader_messages.leader_session_id
--         AND leader_agent_results.sequence_number = leader_messages.sequence_number
--   );

-- DELETE FROM leader_messages
-- WHERE message_type IN ('final_report', 'summary')
--   AND EXISTS (
--       SELECT 1 FROM leader_final_reports
--       WHERE leader_final_reports.leader_session_id = leader_messages.leader_session_id
--   );

-- ============================================================
-- 完成提示
-- ============================================================
-- 迁移完成后，请：
-- 1. 检查验证结果是否符合预期
-- 2. 运行完整测试套件验证功能
-- 3. 确认无误后再执行清理步骤
