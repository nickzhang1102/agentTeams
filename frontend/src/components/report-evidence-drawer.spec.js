import { describe, expect, it, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ReportEvidenceDrawer from './ReportEvidenceDrawer.vue'
import api from '@/utils/api'

vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn()
  }
}))

const evidence = {
  evidence_id: 'ev_result_8',
  source_type: 'web',
  title: 'Result 8',
  excerpt: 'Short summary',
  url: 'https://example.com/result-8',
  completeness: 'passage',
  locator: { page: 4 }
}

const stubs = {
  ElDrawer: { template: '<section><slot /></section>' },
  ElTag: { template: '<span><slot /></span>' },
  ElTooltip: { template: '<span><slot /></span>' },
  ElButton: { template: '<button @click="$emit(\'click\')"><slot /></button>' },
  ElSkeleton: { template: '<div class="skeleton" />' },
  ElEmpty: { template: '<div class="empty" />' }
}

function createWrapper(props = {}) {
  return mount(ReportEvidenceDrawer, {
    props: {
      modelValue: true,
      evidenceMap: [evidence],
      sessionId: 42,
      ...props
    },
    global: { stubs }
  })
}

describe('ReportEvidenceDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('deduplicates an in-flight detail request and caches the passage', async () => {
    let resolveRequest
    api.get.mockReturnValue(new Promise(resolve => {
      resolveRequest = resolve
    }))
    const wrapper = createWrapper()

    const first = wrapper.vm.loadDetail(evidence)
    const second = wrapper.vm.loadDetail(evidence)

    expect(api.get).toHaveBeenCalledTimes(1)
    expect(api.get).toHaveBeenCalledWith(
      '/api/leader/sessions/42/evidence/ev_result_8',
      { suppressGlobalError: true }
    )

    resolveRequest({
      data: {
        ...evidence,
        passage: 'Full relevant passage beyond the old truncation.',
        content_hash: 'abc123'
      }
    })
    await Promise.all([first, second])
    await wrapper.vm.loadDetail(evidence)

    expect(api.get).toHaveBeenCalledTimes(1)
    expect(wrapper.vm.detailState(evidence).status).toBe('success')
    expect(wrapper.vm.detailState(evidence).data.passage).toContain('beyond the old truncation')
  })

  it('loads an initially highlighted evidence when restoring an open drawer', async () => {
    api.get.mockResolvedValue({
      data: {
        ...evidence,
        passage: 'Restored evidence passage'
      }
    })

    const wrapper = createWrapper({ highlightId: evidence.evidence_id })
    await flushPromises()

    expect(wrapper.vm.expandedId).toBe(evidence.evidence_id)
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.evidence-passage').text()).toBe('Restored evidence passage')
  })

  it('does not expose or load owner-only detail when the capability is disabled', async () => {
    api.get.mockResolvedValue({
      data: {
        ...evidence,
        passage: 'This passage must not be requested'
      }
    })

    const wrapper = createWrapper({
      detailEnabled: false,
      highlightId: evidence.evidence_id
    })
    await flushPromises()
    await wrapper.vm.loadDetail(evidence)
    await wrapper.vm.toggleDetail(evidence)

    expect(wrapper.find('.evidence-detail-toggle').exists()).toBe(false)
    expect(wrapper.vm.expandedId).toBe('')
    expect(api.get).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Short summary')
  })

  it('keeps legacy resolution failures local to the selected evidence', async () => {
    api.get.mockRejectedValue({ response: { status: 422 } })
    const wrapper = createWrapper()

    await wrapper.vm.toggleDetail(evidence)
    await flushPromises()

    expect(wrapper.vm.expandedId).toBe('ev_result_8')
    expect(wrapper.vm.detailState(evidence).status).toBe('unresolvable')
    expect(wrapper.text()).toContain('旧版证据无法精确解析')
    expect(wrapper.text()).toContain('证据详情暂时无法加载')
    expect(wrapper.text().match(/Short summary/g)).toHaveLength(1)

    await wrapper.vm.toggleDetail(evidence)
    expect(wrapper.find('.evidence-detail').exists()).toBe(false)
    expect(wrapper.text().match(/Short summary/g)).toHaveLength(1)
  })

  it('renders a loaded passage inside the evidence item', async () => {
    api.get.mockResolvedValue({
      data: {
        ...evidence,
        passage: 'A stable full passage',
        completeness: 'snippet'
      }
    })
    const wrapper = createWrapper()

    await wrapper.vm.toggleDetail(evidence)
    await flushPromises()

    expect(wrapper.find('.evidence-passage').text()).toBe('A stable full passage')
    expect(wrapper.text()).toContain('当前来源仅提供摘要片段')
  })

  it('opens only http or https source URLs', () => {
    const wrapper = createWrapper()
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)

    wrapper.vm.openSource('javascript:alert(1)')
    wrapper.vm.openSource('https://example.com/source')

    expect(open).toHaveBeenCalledTimes(1)
    expect(open).toHaveBeenCalledWith(
      'https://example.com/source',
      '_blank',
      'noopener,noreferrer'
    )
    open.mockRestore()
  })
})
