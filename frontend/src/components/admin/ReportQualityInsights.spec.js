import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import ReportQualityInsights from './ReportQualityInsights.vue'
import { applyLocale } from '@/locales'

const fetchReportQualityInsights = vi.fn()
const storeState = {
  reportQualityInsights: null,
  reportQualityInsightsLoading: false,
  reportQualityInsightsError: null,
  fetchReportQualityInsights
}

vi.mock('@/stores/admin', () => ({
  useAdminStore: () => storeState
}))

function mountComponent() {
  return shallowMount(ReportQualityInsights, {
    global: {
      stubs: {
        ElSegmented: {
          props: ['modelValue', 'options'],
          emits: ['update:modelValue', 'change'],
          template: '<button class="period-switch" @click="$emit(\'update:modelValue\', \'7d\'); $emit(\'change\', \'7d\')">7 天</button>'
        },
        ElSkeleton: true,
        ElEmpty: {
          props: ['description'],
          template: '<div class="empty-state">{{ description }}<slot /></div>'
        },
        ElButton: {
          template: '<button><slot /></button>'
        },
        ElProgress: true,
        ElTag: {
          template: '<span class="el-tag"><slot /></span>'
        },
        ElTable: {
          props: ['data'],
          template: '<div class="el-table"><slot v-for="row in data" :row="row" /></div>'
        },
        ElTableColumn: {
          props: ['label', 'prop'],
          template: '<div class="el-table-column"><slot :row="$parent?.row || {}" /></div>'
        }
      }
    }
  })
}

describe('ReportQualityInsights', () => {
  beforeEach(() => {
    applyLocale('zh-CN')
    fetchReportQualityInsights.mockReset()
    fetchReportQualityInsights.mockResolvedValue({})
    storeState.reportQualityInsights = {
      period_days: 30,
      summary: {
        total_ratings: 3,
        positive_count: 1,
        negative_count: 2,
        positive_rate: 33.3,
        negative_rate: 66.7
      },
      target_breakdown: [
        {
          target_type: 'agent_result',
          total: 2,
          positive_rate: 50.0,
          negative_rate: 50.0
        }
      ],
      problem_clusters: [
        {
          key: 'evidence_gap',
          label: '证据不足',
          count: 1,
          share: 50.0,
          examples: ['缺少来源，证据不够']
        }
      ],
      recent_negative_comments: [
        {
          id: 1,
          target_type: 'final_report',
          target_id: 9,
          comment: '结论不清楚，建议不可执行',
          created_at: '2026-06-26T10:00:00Z'
        }
      ]
    }
    storeState.reportQualityInsightsLoading = false
    storeState.reportQualityInsightsError = null
  })

  it('渲染报告质量摘要、问题聚类和最近差评', () => {
    const wrapper = mountComponent()

    expect(wrapper.text()).toContain('报告质量洞察')
    expect(wrapper.text()).toContain('总评分')
    expect(wrapper.text()).toContain('33.3%')
    expect(wrapper.text()).toContain('66.7%')
    expect(wrapper.text()).toContain('证据不足')
    expect(wrapper.text()).toContain('缺少来源，证据不够')
    expect(wrapper.text()).toContain('结论不清楚，建议不可执行')
    expect(fetchReportQualityInsights).toHaveBeenCalledWith('30d')
  })

  it('切换周期时重新请求质量洞察', async () => {
    const wrapper = mountComponent()

    await wrapper.find('.period-switch').trigger('click')

    expect(fetchReportQualityInsights).toHaveBeenCalledWith('7d')
  })

  it('无评分时显示空态', () => {
    storeState.reportQualityInsights = {
      period_days: 30,
      summary: {
        total_ratings: 0,
        positive_count: 0,
        negative_count: 0,
        positive_rate: 0,
        negative_rate: 0
      },
      target_breakdown: [],
      problem_clusters: [],
      recent_negative_comments: []
    }

    const wrapper = mountComponent()

    expect(wrapper.text()).toContain('当前周期暂无报告评分')
  })

  it('切换语言后更新组件固定文案并保留评论原文', async () => {
    const wrapper = mountComponent()

    applyLocale('en-US')
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('Report quality insights')
    expect(wrapper.text()).toContain('Total ratings')
    expect(wrapper.text()).toContain('缺少来源，证据不够')
    expect(wrapper.text()).toContain('结论不清楚，建议不可执行')
  })
})
