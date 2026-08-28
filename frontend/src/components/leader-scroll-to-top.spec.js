import { describe, it, expect, beforeEach, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => ({
  leaderStore: {
    leaderState: 'completed',
    totalTime: 42,
    finalReport: '',
    selectedAgents: [],
    agentStatuses: [],
    agentResults: [],
    agentExecutionOrder: {},
    sessions: []
  }
}))

vi.mock('@/stores/leader', () => ({
  useLeaderStore: () => mocks.leaderStore
}))

vi.mock('@element-plus/icons-vue', () => ({
  Document: () => null,
  UserFilled: () => null,
  Loading: () => null,
  Tools: () => null,
  List: () => null,
  Check: () => null,
  Close: () => null,
  Clock: () => null,
  Plus: () => null
}))

const PassThroughStub = defineComponent({
  name: 'PassThroughStub',
  inheritAttrs: false,
  setup(props, { slots, attrs }) {
    return () => h('div', attrs, slots.default ? slots.default() : [])
  }
})

const LeaderThinkingStub = defineComponent({
  name: 'LeaderThinkingStub',
  setup() {
    return () => h('div', { 'data-testid': 'leader-thinking' }, 'LeaderThinking')
  }
})

describe('Leader review scroll-to-top integration', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mocks.leaderStore.leaderState = 'completed'
    mocks.leaderStore.totalTime = 42
    mocks.leaderStore.finalReport = ''
    mocks.leaderStore.selectedAgents = []
    mocks.leaderStore.agentStatuses = []
    mocks.leaderStore.agentResults = []
    mocks.leaderStore.agentExecutionOrder = {}
    mocks.leaderStore.sessions = []
  })

  it('LeaderFinalReport 应正确渲染最终报告', async () => {
    mocks.leaderStore.finalReport = '最终报告内容'.repeat(100)
    const { default: LeaderFinalReport } = await import('@/components/LeaderFinalReport.vue')

    const wrapper = shallowMount(LeaderFinalReport, {
      props: {
        conversationId: '42'
      },
      global: {
        stubs: {
          ChatActionBar: true,
          SuggestedQuestions: true,
          ReportEvidenceDrawer: true,
          ReportVisualBlocks: true,
          'el-button': PassThroughStub,
          'el-collapse': PassThroughStub,
          'el-collapse-item': PassThroughStub,
          'el-icon': PassThroughStub
        }
      }
    })

    await nextTick()

    // 验证最终报告正确渲染
    expect(wrapper.find('.final-report').exists()).toBe(true)
    expect(wrapper.find('.report-header').exists()).toBe(true)
  })

  it('LeaderFinalReport 降级 Markdown 报告不应把字符串 executive_summary 当摘要卡', async () => {
    mocks.leaderStore.finalReport = {
      report: '# 完整报告\n\n详细分析内容',
      summary: null,
      executive_summary: '这不是结构化摘要对象',
      structured_report: null
    }
    const { default: LeaderFinalReport } = await import('@/components/LeaderFinalReport.vue')

    const wrapper = shallowMount(LeaderFinalReport, {
      props: {
        conversationId: '42'
      },
      global: {
        stubs: {
          ChatActionBar: true,
          SuggestedQuestions: true,
          ReportEvidenceDrawer: true,
          ReportVisualBlocks: true,
          'el-button': PassThroughStub,
          'el-collapse': PassThroughStub,
          'el-collapse-item': PassThroughStub,
          'el-icon': PassThroughStub
        }
      }
    })

    await nextTick()

    expect(wrapper.find('.report-summary').exists()).toBe(false)
    expect(wrapper.find('.report-detail-collapse').exists()).toBe(false)
  })

  it('LeaderFinalReport 有摘要和证据时应摘要优先并折叠全文', async () => {
    mocks.leaderStore.finalReport = {
      content: '# 完整报告\n\n详细分析内容',
      summary: {
        executive_summary: '这是执行摘要',
        key_findings: ['关键发现 A'],
        recommendations: ['建议 A'],
        risks: ['风险 A']
      },
      evidence_map: [
        {
          title: '证据 1',
          excerpt: '证据摘录',
          source_type: 'tool',
          agent_id: 'agent-a'
        }
      ]
    }
    const { default: LeaderFinalReport } = await import('@/components/LeaderFinalReport.vue')

    const wrapper = shallowMount(LeaderFinalReport, {
      props: {
        conversationId: '42'
      },
      global: {
        stubs: {
          ChatActionBar: true,
          SuggestedQuestions: true,
          ReportEvidenceDrawer: true,
          ReportVisualBlocks: true,
          'el-button': PassThroughStub,
          'el-collapse': PassThroughStub,
          'el-collapse-item': PassThroughStub,
          'el-icon': PassThroughStub
        }
      }
    })

    await nextTick()

    expect(wrapper.find('.report-summary').text()).toContain('这是执行摘要')
    expect(wrapper.text()).toContain('证据 1')
    expect(wrapper.find('.report-detail-collapse').exists()).toBe(true)
  })

  it('LeaderFinalReport 摘要短文本应渲染行内 Markdown', async () => {
    mocks.leaderStore.finalReport = {
      content: '# 完整报告\n\n详细分析内容',
      summary: {
        title: '**摘要**',
        executive_summary: '需要**与主管医生沟通**后再执行',
        key_findings: ['确认 **用药史**'],
        recommendations: ['**与主管医生沟通**'],
        risks: ['避免 <script>alert(1)</script> 注入']
      }
    }
    const { default: LeaderFinalReport } = await import('@/components/LeaderFinalReport.vue')

    const wrapper = shallowMount(LeaderFinalReport, {
      props: {
        conversationId: '42'
      },
      global: {
        stubs: {
          ChatActionBar: true,
          SuggestedQuestions: true,
          ReportEvidenceDrawer: true,
          ReportVisualBlocks: true,
          'el-button': PassThroughStub,
          'el-collapse': PassThroughStub,
          'el-collapse-item': PassThroughStub,
          'el-icon': PassThroughStub
        }
      }
    })

    await nextTick()

    expect(wrapper.find('.summary-lead').html()).toContain('<strong>与主管医生沟通</strong>')
    expect(wrapper.find('.report-summary').html()).toContain('<strong>用药史</strong>')
    expect(wrapper.find('.report-summary').html()).not.toContain('**与主管医生沟通**')
    expect(wrapper.find('.report-summary').html()).not.toContain('<script>')
  })

  it('LeaderFinalReport 应挂载 structured_report.visual_blocks', async () => {
    mocks.leaderStore.finalReport = {
      report: '# 完整报告\n\n详细分析内容',
      summary: {
        executive_summary: '这是执行摘要'
      },
      structured_report: {
        visual_blocks: [
          {
            block_id: 'risk-main',
            type: 'risk_matrix',
            title: '关键风险矩阵',
            data: { risks: [{ risk: '预算超支' }] }
          }
        ]
      }
    }
    const { default: LeaderFinalReport } = await import('@/components/LeaderFinalReport.vue')

    const wrapper = shallowMount(LeaderFinalReport, {
      props: {
        conversationId: '42'
      },
      global: {
        stubs: {
          ChatActionBar: true,
          SuggestedQuestions: true,
          ReportEvidenceDrawer: true,
          ReportVisualBlocks: true,
          'el-button': PassThroughStub,
          'el-collapse': PassThroughStub,
          'el-collapse-item': PassThroughStub,
          'el-icon': PassThroughStub
        }
      }
    })

    await nextTick()

    const visualBlocks = wrapper.findComponent({ name: 'ReportVisualBlocks' })
    expect(visualBlocks.exists()).toBe(true)
    expect(visualBlocks.props('blocks')).toHaveLength(1)
    expect(visualBlocks.props('blocks')[0].type).toBe('risk_matrix')
  })

  it('AgentStatusPanel 应正确渲染已完成的 Agent 结果', async () => {
    mocks.leaderStore.selectedAgents = [{ agent_id: 'cardio', agent_name: '心血管内科专家' }]
    mocks.leaderStore.agentStatuses = [{ agent_id: 'cardio', status: 'completed' }]
    mocks.leaderStore.agentResults = [{ agent_id: 'cardio', content: '分析内容' }]
    mocks.leaderStore.agentExecutionOrder = {
      cardio: { batchIndex: 0, agentIndex: 0, sequence: 0 }
    }
    const { default: AgentStatusPanel } = await import('@/components/AgentStatusPanel.vue')

    const wrapper = shallowMount(AgentStatusPanel, {
      props: {
        conversationId: '42'
      },
      global: {
        stubs: {
          ChatActionBar: true,
          ReportFeedback: true,
          ReportEvidenceDrawer: true,
          'el-button': PassThroughStub,
          'el-icon': PassThroughStub,
          'el-avatar': PassThroughStub,
          'el-tag': PassThroughStub,
          'el-collapse': PassThroughStub,
          'el-collapse-item': PassThroughStub
        }
      }
    })

    await nextTick()

    // 验证面板正确渲染
    expect(wrapper.find('.agent-status-panel').exists()).toBe(true)
    expect(wrapper.find('.agent-list').exists()).toBe(true)
    expect(wrapper.find('.execution-plan').exists()).toBe(true)
    expect(wrapper.find('.stage-card').exists()).toBe(true)

    // 无持久化 id 的实时占位结果不应渲染评分组件
    expect(wrapper.findComponent({ name: 'ReportFeedback' }).exists()).toBe(false)
  })

  it('AgentStatusPanel 应显示 embed 进度快照中已就绪的单个 Agent 报告', async () => {
    mocks.leaderStore.selectedAgents = [{ agent_id: 'cardio', agent_name: '心血管内科专家' }]
    mocks.leaderStore.agentStatuses = [{
      agent_id: 'cardio',
      status: 'completed',
      content: '第一位专家实时报告',
    }]
    mocks.leaderStore.agentResults = []
    mocks.leaderStore.agentExecutionOrder = {
      cardio: { batchIndex: 0, agentIndex: 0, sequence: 0 }
    }
    const { default: AgentStatusPanel } = await import('@/components/AgentStatusPanel.vue')

    const wrapper = shallowMount(AgentStatusPanel, {
      props: { conversationId: '42' },
      global: {
        stubs: {
          ChatActionBar: true,
          ReportFeedback: true,
          ReportEvidenceDrawer: true,
          'el-button': PassThroughStub,
          'el-icon': PassThroughStub,
          'el-avatar': PassThroughStub,
          'el-tag': PassThroughStub,
          'el-collapse': PassThroughStub,
          'el-collapse-item': PassThroughStub
        }
      }
    })

    await nextTick()

    expect(wrapper.html()).toContain('第一位专家实时报告')
  })

  it('AgentStatusPanel 应将并行 Agent 渲染为同一阶段', async () => {
    mocks.leaderStore.selectedAgents = [
      { agent_id: 'planner', agent_name: '规划专家' },
      { agent_id: 'coder', agent_name: '编码专家' },
      { agent_id: 'reviewer', agent_name: '评审专家' }
    ]
    mocks.leaderStore.agentStatuses = [
      { agent_id: 'planner', status: 'completed' },
      { agent_id: 'coder', status: 'running' },
      { agent_id: 'reviewer', status: 'running' }
    ]
    mocks.leaderStore.agentResults = []
    mocks.leaderStore.agentExecutionOrder = {
      planner: { batchIndex: 0, agentIndex: 0, sequence: 0 },
      coder: { batchIndex: 1, agentIndex: 0, sequence: 1 },
      reviewer: { batchIndex: 1, agentIndex: 1, sequence: 2 }
    }

    const { default: AgentStatusPanel } = await import('@/components/AgentStatusPanel.vue')
    const wrapper = shallowMount(AgentStatusPanel, {
      props: {
        conversationId: '42'
      },
      global: {
        stubs: {
          ChatActionBar: true,
          ReportFeedback: true,
          ReportEvidenceDrawer: true,
          'el-button': PassThroughStub,
          'el-icon': PassThroughStub,
          'el-avatar': PassThroughStub,
          'el-tag': PassThroughStub,
          'el-collapse': PassThroughStub,
          'el-collapse-item': PassThroughStub
        }
      }
    })

    await nextTick()

    const stageCards = wrapper.findAll('.stage-card')
    expect(stageCards).toHaveLength(2)
    expect(stageCards[1].text()).toContain('并行阶段')
    expect(stageCards[1].findAll('.stage-agent-chip')).toHaveLength(2)
  })

  it('AgentStatusPanel 应忽略 Agent 摘要并默认展示正文', async () => {
    mocks.leaderStore.selectedAgents = [
      { agent_id: 'planner', agent_name: '规划专家' },
      { agent_id: 'reviewer', agent_name: '评审专家' }
    ]
    mocks.leaderStore.agentStatuses = [
      { agent_id: 'planner', status: 'completed' },
      { agent_id: 'reviewer', status: 'completed' }
    ]
    mocks.leaderStore.agentResults = [
      {
        agent_id: 'planner',
        content: '规划完整分析',
        summary: {
          one_sentence: '规划结论',
          recommendations: ['规划建议'],
          risks: ['规划风险'],
          confidence: 0.9
        },
        evidence_map: [
          {
            title: '证据 1',
            excerpt: '规划证据摘录',
            source_type: 'tool'
          }
        ]
      },
      {
        agent_id: 'reviewer',
        content: '评审完整分析',
        summary: {
          one_sentence: '评审结论',
          recommendations: ['评审建议'],
          risks: ['评审风险'],
          confidence: 0.7
        }
      }
    ]
    mocks.leaderStore.agentExecutionOrder = {
      planner: { batchIndex: 0, agentIndex: 0, sequence: 0 },
      reviewer: { batchIndex: 1, agentIndex: 0, sequence: 1 }
    }

    const { default: AgentStatusPanel } = await import('@/components/AgentStatusPanel.vue')
    const wrapper = shallowMount(AgentStatusPanel, {
      props: {
        conversationId: '42'
      },
      global: {
        stubs: {
          ChatActionBar: true,
          ReportFeedback: true,
          ReportEvidenceDrawer: true,
          'el-button': PassThroughStub,
          'el-icon': PassThroughStub,
          'el-avatar': PassThroughStub,
          'el-tag': PassThroughStub,
          'el-collapse': PassThroughStub,
          'el-collapse-item': PassThroughStub
        }
      }
    })

    await nextTick()

    expect(wrapper.find('.agent-opinion-compare').exists()).toBe(false)
    expect(wrapper.find('.agent-summary').exists()).toBe(false)
    expect(wrapper.find('.agent-report-collapse').exists()).toBe(false)
    expect(wrapper.html()).toContain('规划完整分析')
    expect(wrapper.html()).toContain('评审完整分析')
    expect(wrapper.html()).not.toContain('规划结论')
    expect(wrapper.text()).toContain('证据 1')
  })
  it('AgentStatusPanel 点击证据引用（含跨 Agent 引用）时应打开全会话合并证据上下文', async () => {
    mocks.leaderStore.selectedAgents = [
      { agent_id: 'planner', agent_name: '规划专家' },
      { agent_id: 'reviewer', agent_name: '评审专家' }
    ]
    mocks.leaderStore.agentStatuses = [
      { agent_id: 'planner', status: 'completed' },
      { agent_id: 'reviewer', status: 'completed' }
    ]
    mocks.leaderStore.agentResults = [
      {
        agent_id: 'planner',
        content: '规划完整分析',
        summary: { one_sentence: '规划结论', confidence: 0.9 },
        evidence_map: [{ evidence_id: 'planner_ev_subtask_1_web_search_1', title: '规划证据' }]
      },
      {
        agent_id: 'reviewer',
        content: '评审完整分析',
        summary: { one_sentence: '评审结论', confidence: 0.8 },
        evidence_map: [{ evidence_id: 'reviewer_ev_subtask_1_web_search_1', title: '评审证据' }]
      }
    ]
    mocks.leaderStore.agentExecutionOrder = {
      planner: { batchIndex: 0, agentIndex: 0, sequence: 0 },
      reviewer: { batchIndex: 1, agentIndex: 0, sequence: 1 }
    }

    const { default: AgentStatusPanel } = await import('@/components/AgentStatusPanel.vue')
    const wrapper = shallowMount(AgentStatusPanel, {
      props: {
        conversationId: '42'
      },
      global: {
        stubs: {
          ChatActionBar: true,
          ReportFeedback: true,
          ReportEvidenceDrawer: true,
          'el-button': PassThroughStub,
          'el-icon': PassThroughStub,
          'el-avatar': PassThroughStub,
          'el-tag': PassThroughStub,
          'el-collapse': PassThroughStub,
          'el-collapse-item': PassThroughStub
        }
      }
    })

    await nextTick()

    wrapper.vm.openAgentEvidence(mocks.leaderStore.agentResults[0])
    wrapper.vm.handleAgentEvidenceClick(
      mocks.leaderStore.agentResults[1],
      'reviewer_ev_subtask_1_web_search_1'
    )
    await nextTick()

    const drawer = wrapper.findComponent({ name: 'ReportEvidenceDrawer' })
    // 报告正文可能引用其他 Agent 的证据（批次上下文中的 scoped evidence_id），
    // 点击引用时抽屉应拿到全会话合并证据表，保证跨 Agent 引用可定位。
    expect(drawer.props('evidenceMap')).toEqual([
      { evidence_id: 'planner_ev_subtask_1_web_search_1', title: '规划证据' },
      { evidence_id: 'reviewer_ev_subtask_1_web_search_1', title: '评审证据' }
    ])
    expect(drawer.props('highlightId')).toBe('reviewer_ev_subtask_1_web_search_1')
  })
})
