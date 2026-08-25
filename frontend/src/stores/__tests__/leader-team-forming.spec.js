import { setActivePinia, createPinia } from 'pinia'
import { useLeaderStore } from '@/stores/leader'

describe('Leader Store - Team Forming Events', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('handleTeamForming', () => {
    it('should handle analyzing phase', () => {
      const store = useLeaderStore()

      const data = {
        type: 'team_forming',
        session_id: 17,
        phase: 'analyzing',
        content: '正在分析需求并选择最合适的专家团队...'
      }

      store.handleTeamForming(data)

      expect(store.leaderState).toBe('forming_team')
      expect(store.currentPhase).toBe('forming_team')
      expect(store.thinkingContent).toBe('正在分析需求并选择最合适的专家团队...')
    })

    it('should handle selection_complete phase with JSON content', () => {
      const store = useLeaderStore()

      const selectionData = {
        analysis: '用户需求涉及74岁胰腺癌晚期伴肝转移患者的综合治疗。',
        selected_agents: [
          {
            agent_id: 'oncology-expert',
            agent_name: '肿瘤内科专家',
            reason: '核心专家。负责制定晚期胰腺癌的系统性治疗方案。'
          },
          {
            agent_id: 'tcm-expert',
            agent_name: '中医科专家',
            reason: '提供中西医结合支持。'
          }
        ],
        team_strategy: '采用MDT多学科协作模式：肿瘤内科专家作为主导...'
      }

      const data = {
        type: 'team_forming',
        session_id: 17,
        phase: 'selection_complete',
        content: JSON.stringify(selectionData)
      }

      store.handleTeamForming(data)

      expect(store.leaderState).toBe('forming_team')
      expect(store.currentPhase).toBe('forming_team')
      expect(store.teamAnalysis).toBe(selectionData.analysis)
      expect(store.teamStrategy).toBe(selectionData.team_strategy)

      // 验证 thinkingContent 包含分析内容
      expect(store.thinkingContent).toContain('## 需求分析')
      expect(store.thinkingContent).toContain(selectionData.analysis)
      expect(store.thinkingContent).toContain('## 团队策略')
      expect(store.thinkingContent).toContain(selectionData.team_strategy)
      expect(store.thinkingContent).toContain('## 选定的专家团队')
      expect(store.thinkingContent).toContain('肿瘤内科专家')
      expect(store.thinkingContent).toContain('中医科专家')
    })

    it('should handle selection_complete phase with object content', () => {
      const store = useLeaderStore()

      const selectionData = {
        analysis: '测试分析',
        selected_agents: [
          {
            agent_id: 'test-agent',
            agent_name: '测试专家',
            reason: '测试原因'
          }
        ],
        team_strategy: '测试策略'
      }

      const data = {
        type: 'team_forming',
        session_id: 17,
        phase: 'selection_complete',
        content: selectionData // 直接传递对象
      }

      store.handleTeamForming(data)

      expect(store.teamAnalysis).toBe('测试分析')
      expect(store.teamStrategy).toBe('测试策略')
      expect(store.thinkingContent).toContain('测试专家')
    })

    it('should handle legacy format with candidates', () => {
      const store = useLeaderStore()

      const data = {
        type: 'team_forming',
        session_id: 17,
        candidates: [
          { agent_id: 'agent1', agent_name: '专家1' }
        ],
        progress: '正在选择专家...'
      }

      store.handleTeamForming(data)

      expect(store.teamCandidates).toHaveLength(1)
      expect(store.thinkingContent).toBe('正在选择专家...')
    })
  })

  describe('handleTeamReady', () => {
    it('should display complete team information', () => {
      const store = useLeaderStore()

      const data = {
        type: 'team_ready',
        session_id: 17,
        team: {
          name: '智能团队 - 胰腺癌治疗',
          description: '采用MDT多学科协作模式',
          aggregation_mode: 'leader-summary',
          dag_plan: {
            execution_batches: [
              { priority: 40, agents: ['oncology-expert'] },
              { priority: 50, agents: ['tcm-expert'] }
            ]
          },
          agents: [
            {
              agent_id: 'oncology-expert',
              agent_name: '肿瘤内科专家',
              reason: '负责制定系统性治疗方案'
            },
            {
              agent_id: 'tcm-expert',
              agent_name: '中医科专家',
              reason: '提供中西医结合支持'
            }
          ]
        }
      }

      store.handleTeamReady(data)

      expect(store.leaderState).toBe('monitoring')
      expect(store.currentPhase).toBe('monitoring')
      expect(store.selectedAgents).toHaveLength(2)
      expect(store.agentExecutionOrder['oncology-expert'].sequence).toBe(0)
      expect(store.agentExecutionOrder['tcm-expert'].sequence).toBe(1)

      // 验证 thinkingContent 包含团队信息
      expect(store.thinkingContent).toContain('## 团队已组建完成')
      expect(store.thinkingContent).toContain('智能团队 - 胰腺癌治疗')
      expect(store.thinkingContent).toContain('采用MDT多学科协作模式')
      expect(store.thinkingContent).toContain('团队成员')
      expect(store.thinkingContent).toContain('肿瘤内科专家')
      expect(store.thinkingContent).toContain('中医科专家')
      expect(store.thinkingContent).toContain('负责制定系统性治疗方案')
      expect(store.thinkingContent).toContain('提供中西医结合支持')
    })

    it('should handle team without description', () => {
      const store = useLeaderStore()

      const data = {
        type: 'team_ready',
        session_id: 17,
        team: {
          name: '测试团队',
          agents: [
            {
              agent_id: 'agent1',
              agent_name: '专家1'
            }
          ]
        }
      }

      store.handleTeamReady(data)

      expect(store.thinkingContent).toContain('测试团队')
      expect(store.thinkingContent).toContain('专家1')
    })
  })

  describe('resetState', () => {
    it('should clear team analysis and strategy', () => {
      const store = useLeaderStore()

      // 设置一些状态
      store.teamAnalysis = '测试分析'
      store.teamStrategy = '测试策略'
      store.thinkingContent = '测试内容'

      store.resetState()

      expect(store.teamAnalysis).toBe('')
      expect(store.teamStrategy).toBe('')
      expect(store.thinkingContent).toBe('')
    })
  })
})
