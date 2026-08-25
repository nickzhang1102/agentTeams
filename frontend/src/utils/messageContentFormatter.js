/**
 * 消息内容格式化工具
 *
 * 将 Message 表 JSONB content 字段按 message_type 格式化为可读 Markdown 文本。
 * 统一 ConversationDisplay.vue 和 leader.js 中的重复格式化逻辑。
 */

import { i18n } from '@/locales'

/**
 * 获取阶段标签
 * @param {string} phase - 阶段标识
 * @returns {string} 中文标签
 */
function getPhaseText(phase, isEnglish = false) {
  const map = isEnglish ? {
    analyzing: 'Requirement analysis',
    selecting: 'Expert selection',
    forming: 'Team formation',
    executing: 'Executing',
    monitoring: 'Monitoring',
    summarizing: 'Summarizing',
    ai_analyzing: 'AI analysis',
    claude_analyzing: 'AI analysis',
    assessing: 'Assessing',
    forming_team: 'Team formation',
    selection_complete: 'Selection complete',
    api_retry: 'Retrying',
    starting: 'Starting'
  } : {
    analyzing: '需求分析', selecting: '专家选择', forming: '团队组建', executing: '执行中',
    monitoring: '监控中', summarizing: '汇总中', ai_analyzing: 'AI 分析中',
    claude_analyzing: 'AI 分析中', assessing: '评估中', forming_team: '团队组建',
    selection_complete: '选择完成', api_retry: '重试中', starting: '启动中'
  }
  return map[phase] || phase || (isEnglish ? 'Processing' : '处理中')
}

/**
 * 解析可能包含搜索结果 JSON 的文本字段
 * 处理 text 字段为 JSON 字符串的情况（搜索结果、团队选择分析等）
 * @param {string} text - 可能包含 JSON 的文本
 * @param {string} phase - 阶段标识（用于标题）
 * @returns {string|null} 格式化后的 Markdown，无法解析返回 null
 */
function parseJsonText(text, phase = '', isEnglish = false) {
  if (!text || typeof text !== 'string') return null
  const trimmed = text.trim()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null

  try {
    const parsed = JSON.parse(trimmed)

    // 团队选择分析结构
    if (parsed.analysis && parsed.selected_agents) {
      return (isEnglish ? '## Team selection analysis\n\n' : '## 团队选择分析\n\n') +
        `${isEnglish ? '### Requirement analysis' : '### 需求分析'}\n${parsed.analysis}\n\n` +
        (isEnglish ? '### Selected expert team\n' : '### 选定的专家团队\n') +
        (parsed.selected_agents || []).map((agent, i) =>
          `${i + 1}. **${agent.agent_name}** - ${agent.reason}`
        ).join('\n')
    }

    // 搜索结果数组：只显示带超链接的标题
    if (Array.isArray(parsed)) {
      return `## ${getPhaseText(phase, isEnglish)}\n\n` +
        parsed.map((item, i) => {
          if (item.url && item.title) {
            return `${i + 1}. [${item.title}](${item.url})`
          }
          if (item.title) {
            return `${i + 1}. ${item.title}`
          }
          return ''
        }).filter(Boolean).join('\n') || `## ${getPhaseText(phase, isEnglish)}\n\n${trimmed}`
    }

    // 单个搜索结果对象
    if (parsed.title) {
      const link = parsed.url ? `[${parsed.title}](${parsed.url})` : parsed.title
      return `## ${getPhaseText(phase, isEnglish)}\n\n${link}`
    }

    // 有 text/message/content 字段的对象
    if (parsed.text || parsed.message || parsed.content) {
      return `## ${getPhaseText(phase, isEnglish)}\n\n${parsed.text || parsed.message || (typeof parsed.content === 'string' ? parsed.content : '')}`
    }

    // 无法提取有用信息的 JSON：降级为原始文本
    return null
  } catch {
    return null
  }
}

/**
 * 将搜索结果数组格式化为超链接列表
 * @param {Array} items - 搜索结果数组
 * @returns {string} Markdown 格式的链接列表
 */
function formatSearchResults(items) {
  return items.map((item, i) => {
    if (item.url && item.title) return `${i + 1}. [${item.title}](${item.url})`
    if (item.title) return `${i + 1}. ${item.title}`
    return ''
  }).filter(Boolean).join('\n') || ''
}

/**
 * 格式化消息内容为可读 Markdown 文本
 *
 * @param {string|object} content - JSONB content 字段（字符串或结构化对象）
 * @param {string} messageType - 消息类型（normal/assessment/question/answer/team_config/progress 等）
 * @returns {string} 格式化后的 Markdown 文本
 */
export function formatMessageContent(content, messageType, locale) {
  // 字符串直接返回
  if (typeof content === 'string') {
    return content
  }

  // 非对象兜底
  if (!content || typeof content !== 'object') {
    return String(content ?? '')
  }

  if (typeof content.message_key === 'string') {
    if (i18n.global.te(content.message_key)) {
      return i18n.global.t(content.message_key, content.message_params || {})
    }
    return content.message || content.content || ''
  }

  const isEnglish = (locale || content.content_locale) === 'en-US'

  switch (messageType) {
    case 'normal':
    case null:
    case undefined:
      // 普通消息：{'text': '...'}，text 可能包含 JSON 搜索结果
      if (content.text) {
        const parsed = parseJsonText(content.text)
        if (parsed) return parsed
        return content.text
      }
      return ''

    case 'assessment': {
      const a = content
      // 兼容两种格式：
      // 1. DB 历史格式: {score, details: {scores, analysis}, risk_level}
      // 2. SSE 实时格式: {assessment: {score, summary, dimensions: [...]}, risk_level}
      const assessment = a.assessment || a
      const score = assessment.score ?? a.score ?? 0
      const analysis = assessment.summary || assessment.details?.analysis || ''
      const riskLevel = assessment.risk_level || a.risk_level || ''

      // 维度评分：优先使用后端已归一化的中文维度名
      let dimensionsText = ''
      const dimensionLabels = {
        '目标明确性': 'Goal clarity', '预期成果': 'Expected outcome', '边界范围': 'Scope boundary',
        '约束条件': 'Constraints', '症状描述': 'Symptom details', '病史信息': 'Medical history',
        '检查结果': 'Test results', '用药情况': 'Current medication', '个人情况': 'Personal context',
        '投资目标': 'Investment goal', '风险偏好': 'Risk preference', '资金规模': 'Capital size',
        '投资期限': 'Investment horizon', '特殊限制': 'Special constraints', '案件背景': 'Case background',
        '当事人身份': 'Party identity', '争议焦点': 'Dispute focus', '期望结果': 'Expected outcome',
        '证据情况': 'Evidence', '话题明确性': 'Topic clarity', '分析深度': 'Analysis depth',
        '关注角度': 'Focus angle', '背景了解': 'Background knowledge', '立场倾向': 'Position preference',
        '决策背景': 'Decision context', '可选方案': 'Options', '决策标准': 'Decision criteria',
        '紧迫程度': 'Urgency', '问题清晰度': 'Question clarity', '背景信息': 'Background information',
        '期望深度': 'Expected depth', '应用场景': 'Use case'
      }
      const formatDimension = (name, value) => {
        const label = isEnglish ? (dimensionLabels[name] || name) : name
        return isEnglish ? `- ${label}: ${value} points` : `- ${label}：${value} 分`
      }
      if (Array.isArray(assessment.dimensions)) {
        dimensionsText = assessment.dimensions
          .map(d => formatDimension(d.name || d.dimension, d.score ?? 0))
          .join('\n')
      } else if (assessment.details?.scores && typeof assessment.details.scores === 'object') {
        dimensionsText = Object.entries(assessment.details.scores)
          .map(([k, v]) => formatDimension(k, v))
          .join('\n')
      }

      let result = isEnglish
        ? `## Requirement Assessment\n\n**Score**: ${score}/100\n\n`
        : `## 需求评估结果\n\n**评分**: ${score}/100 分\n\n`
      if (dimensionsText) {
        result += (isEnglish ? '### Dimension Scores\n' : '### 各维度评分\n') + dimensionsText + '\n\n'
      }
      if (analysis) {
        result += `${isEnglish ? '### Analysis' : '### 分析'}\n${analysis}`
      }
      if (riskLevel) {
        const riskLabels = isEnglish
          ? { low: 'Low risk', medium: 'Medium risk', high: 'High risk' }
          : { low: '低风险', medium: '中风险', high: '高风险' }
        result += `\n\n**${isEnglish ? 'Risk Level' : '风险等级'}**: ${riskLabels[riskLevel] || riskLevel}`
      }
      const riskReason = assessment.risk_reason || assessment.details?.risk_reason || a.risk_reason
      if (riskReason) {
        result += `\n\n**${isEnglish ? 'Risk Rationale' : '风险原因'}**: ${riskReason}`
      }
      return result
    }

    case 'question': {
      if (content.questions && Array.isArray(content.questions)) {
        return (isEnglish ? '## Follow-up Questions\n\n' : '## 需求追问\n\n') +
          content.questions.map((q, i) => {
            const text = typeof q === 'string' ? q : (q?.question || q?.text || JSON.stringify(q))
            return `${i + 1}. ${text}`
          }).join('\n\n')
      }
      return ''
    }

    case 'answer': {
      if (content.answers && Array.isArray(content.answers)) {
        return (isEnglish ? '## User Answers\n\n' : '## 用户回答\n\n') +
          content.answers.map((a, i) => {
            if (typeof a === 'string') return `${i + 1}. ${a}`
            if (a?.question) return `${i + 1}. ${a.question}: ${a.answer || ''}`
            return `${i + 1}. ${a?.answer || JSON.stringify(a)}`
          }).join('\n\n')
      }
      return ''
    }

    case 'team_config': {
      const tc = content
      // 兼容两种格式：
      // 1. DB 历史格式: {mode, team_strategy, agent_details: [...]}
      // 2. SSE 实时格式: {team: {name, description, agents: [...]}}
      const team = tc.team || tc
      const agents = team.agent_details || team.agents || []
      const mode = team.mode || tc.mode
      const strategy = team.team_strategy || team.description || tc.team_strategy || ''
      const teamLabels = isEnglish
        ? { complete: 'Team configuration complete', mode: 'Team mode', parallel: 'Parallel execution', sequential: 'Sequential execution', strategy: 'Team strategy', name: 'Team name', members: 'Team members' }
        : { complete: '团队配置完成', mode: '团队模式', parallel: '并行执行', sequential: '顺序执行', strategy: '团队策略', name: '团队名称', members: '团队成员' }

      let result = `## ${teamLabels.complete}\n\n`
      if (mode) {
        result += `**${teamLabels.mode}**: ${mode === 'parallel' ? teamLabels.parallel : teamLabels.sequential}\n\n`
      }
      if (strategy) {
        result += `**${teamLabels.strategy}**: ${strategy}\n\n`
      }
      if (team.name) {
        result += `**${teamLabels.name}**: ${team.name}\n\n`
      }
      if (agents.length > 0) {
        result += `**${teamLabels.members}** (${agents.length}):\n` +
          agents.map((agent, i) =>
            `${i + 1}. **${agent.agent_name || agent.name || agent.agent_id}**${agent.reason ? ` - ${agent.reason}` : ''}`
          ).join('\n')
      }
      return result
    }

    case 'progress': {
      const progressText = content.text || content.content || content.progress || content.message || ''
      const phase = content.phase || ''

      // text 字段可能包含 JSON 字符串（搜索结果、团队分析等）
      const parsed = parseJsonText(progressText, phase, isEnglish)
      if (parsed) return parsed

      return `## ${getPhaseText(phase, isEnglish)}\n\n${progressText}`
    }

    case 'leader_thinking': {
      const text = content.text || ''
      // leader_thinking 的 text 也可能包含搜索结果 JSON
      const parsed = parseJsonText(text)
      if (parsed) return parsed
      return text
    }

    case 'leader_summarizing': {
      const text = content.text || '正在汇总所有专家意见...'
      const parsed = parseJsonText(text)
      if (parsed) return parsed
      return text
    }

    case 'execution_status': {
      const text = content.text || ''
      const parsed = parseJsonText(text, content.phase || '')
      if (parsed) return parsed
      return text
    }

    case 'error':
      return content.message || content.error || ''

    case 'web_search_result': {
      // web_search_result: {query, summary, citations: [{url, title, snippet}], raw_result}
      const citations = content.citations
      if (Array.isArray(citations) && citations.length > 0) {
        return '## 搜索结果\n\n' +
          citations.map((item, i) => {
            if (item.url && item.title) {
              return `${i + 1}. [${item.title}](${item.url})`
            }
            if (item.title) {
              return `${i + 1}. ${item.title}`
            }
            return ''
          }).filter(Boolean).join('\n')
      }
      // 降级：使用 summary
      if (content.summary) {
        return `## 搜索结果\n\n${content.summary}`
      }
      return ''
    }

    case 'agent_result': {
      // Agent 结果可能是搜索结果
      if (Array.isArray(content)) {
        return formatSearchResults(content) || ''
      }
      const text = content.text || content.content || content.report || ''
      const parsed = parseJsonText(text)
      if (parsed) return parsed
      return typeof text === 'string' ? text : ''
    }

    case 'tool_call': {
      // 工具调用事件：格式化为简洁提示
      const toolName = content.tool_name || ''
      const agentName = content.agent_name || content.agent_id || ''
      if (content.tool_output_summary) {
        // tool_call_completed：显示工具名和结果摘要
        const summary = content.tool_output_summary
        // 尝试解析搜索结果
        const parsed = parseJsonText(summary, 'search')
        if (parsed) return parsed
        // 截断长输出
        const short = summary.length > 200 ? summary.slice(0, 200) + '...' : summary
        return `🔧 **${agentName}** → ${toolName}: ${short}`
      }
      // tool_call_started：仅显示调用提示
      const input = content.tool_input
      if (toolName === 'web_search' && input) {
        const query = typeof input === 'string' ? input : (input.query || JSON.stringify(input))
        return `🔍 **${agentName}** 正在搜索: ${query}`
      }
      return `🔧 **${agentName}** 调用 ${toolName}`
    }

    default: {
      // 未知类型：优先提取文本字段，处理 JSON 搜索结果
      if (content.text) {
        const parsed = parseJsonText(content.text)
        if (parsed) return parsed
        return content.text
      }
      if (content.message) return content.message
      if (content.content && typeof content.content === 'string') {
        const parsed = parseJsonText(content.content)
        if (parsed) return parsed
        return content.content
      }
      // 搜索结果数组
      if (Array.isArray(content)) {
        return formatSearchResults(content) || ''
      }
      return ''
    }
  }
}

/**
 * 从 question 类型消息中提取原始问题数组
 * 用于弹窗恢复等需要结构化数据的场景
 *
 * @param {string|object} content - JSONB content 字段
 * @returns {string[]|null} 问题数组，非 question 类型返回 null
 */
export function extractQuestions(content) {
  if (!content || typeof content !== 'object') return null
  if (content.questions && Array.isArray(content.questions)) {
    return content.questions
  }
  return null
}
