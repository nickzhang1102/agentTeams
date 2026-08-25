import { describe, it, expect } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import ReportVisualBlocks from './ReportVisualBlocks.vue'

describe('ReportVisualBlocks', () => {
  it('渲染风险矩阵', () => {
    const wrapper = shallowMount(ReportVisualBlocks, {
      props: {
        blocks: [
          {
            block_id: 'risk-main',
            type: 'risk_matrix',
            title: '关键风险矩阵',
            data: {
              risks: [
                {
                  risk: '预算超支',
                  likelihood: 'medium',
                  impact: 'high',
                  mitigation: '阶段预算闸门'
                }
              ]
            },
            evidence_refs: ['ev_1']
          }
        ]
      }
    })

    expect(wrapper.find('.report-visual-blocks').exists()).toBe(true)
    expect(wrapper.text()).toContain('关键风险矩阵')
    expect(wrapper.text()).toContain('预算超支')
    expect(wrapper.text()).toContain('阶段预算闸门')
    expect(wrapper.text()).toContain('证据 1')
  })

  it('渲染决策矩阵', () => {
    const wrapper = shallowMount(ReportVisualBlocks, {
      props: {
        blocks: [
          {
            block_id: 'decision-options',
            type: 'decision_matrix',
            title: '方案决策矩阵',
            data: {
              options: [
                {
                  option: '方案 A',
                  pros: ['上线快'],
                  cons: ['扩展性一般'],
                  score: 78,
                  recommendation: '适合短期验证'
                }
              ]
            }
          }
        ]
      }
    })

    expect(wrapper.text()).toContain('方案决策矩阵')
    expect(wrapper.text()).toContain('方案 A')
    expect(wrapper.text()).toContain('上线快')
    expect(wrapper.text()).toContain('78')
  })

  it('未知 type 降级展示 JSON', () => {
    const wrapper = shallowMount(ReportVisualBlocks, {
      props: {
        blocks: [
          {
            block_id: 'future-block',
            type: 'timeline',
            title: '未来时间线',
            data: { items: [{ label: '第一阶段' }] }
          }
        ]
      }
    })

    expect(wrapper.text()).toContain('未来时间线')
    expect(wrapper.find('.unknown-block').text()).toContain('第一阶段')
  })

  it('点击图表块证据引用应向上抛事件', async () => {
    const wrapper = shallowMount(ReportVisualBlocks, {
      props: {
        blocks: [
          {
            block_id: 'risk-main',
            type: 'risk_matrix',
            title: '关键风险矩阵',
            data: { risks: [] },
            evidence_refs: ['planner_ev_subtask_1_web_search_1']
          }
        ]
      }
    })

    await wrapper.find('.evidence-ref-chip').trigger('click')

    expect(wrapper.emitted('evidence-click')).toEqual([
      ['planner_ev_subtask_1_web_search_1']
    ])
  })
})
