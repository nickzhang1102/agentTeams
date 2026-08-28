import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

describe('MarkdownRenderer evidence refs', () => {
  it('单一证据归属明确时直接把相关正文做成证据链接', async () => {
    const wrapper = mount(MarkdownRenderer, {
      props: {
        content: '这是需要核验的关键结论。[evidence_id:planner-agent_ev_subtask_1_web_search_1]',
        evidenceMap: [
          { evidence_id: 'planner-agent_ev_subtask_1_web_search_1', title: '关键来源' }
        ],
        evidenceLabel: '证据'
      }
    })

    await nextTick()

    const linkedContent = wrapper.find('.evidence-linked-content')
    expect(linkedContent.exists()).toBe(true)
    expect(linkedContent.text()).toBe('这是需要核验的关键结论。')
    expect(linkedContent.attributes('role')).toBe('link')
    expect(linkedContent.attributes('data-evidence-id')).toBe('planner-agent_ev_subtask_1_web_search_1')
    expect(wrapper.find('.evidence-ref').exists()).toBe(false)

    await linkedContent.trigger('click')
    expect(wrapper.emitted('evidence-click')).toEqual([['planner-agent_ev_subtask_1_web_search_1']])
  })

  it('报告中多条独立结论分别链接各自证据', async () => {
    const wrapper = mount(MarkdownRenderer, {
      props: {
        content: '结论一。[evidence_id:ev_subtask_1_web_search_1]\n结论二。[evidence_id:ev_subtask_2_web_search_1]',
        evidenceMap: [
          { evidence_id: 'ev_subtask_1_web_search_1', title: '来源一' },
          { evidence_id: 'ev_subtask_2_web_search_1', title: '来源二' }
        ],
        evidenceLabel: '证据'
      }
    })

    await nextTick()

    const linkedContent = wrapper.findAll('.evidence-linked-content')
    expect(linkedContent.map(item => item.text())).toEqual(['结论一。', '结论二。'])
    expect(linkedContent.map(item => item.attributes('data-evidence-id'))).toEqual([
      'ev_subtask_1_web_search_1',
      'ev_subtask_2_web_search_1'
    ])
    expect(wrapper.find('.evidence-ref').exists()).toBe(false)
  })

  it('把 evidence_map 中的显式引用显示为短标签并保留点击目标', async () => {
    const wrapper = mount(MarkdownRenderer, {
      props: {
        content: '结论一。[evidence_id:planner-agent_ev_subtask_1_web_search_1] 结论二。[evidence_id:ev_subtask_2_llm_analysis_1]',
        evidenceMap: [
          { evidence_id: 'planner-agent_ev_subtask_1_web_search_1', title: '来源一' },
          { evidence_id: 'ev_subtask_2_llm_analysis_1', title: '来源二' }
        ],
        evidenceLabel: '证据'
      }
    })

    await nextTick()

    const refs = wrapper.findAll('.evidence-ref')
    expect(refs).toHaveLength(2)
    expect(refs.map(ref => ref.text())).toEqual(['证据1', '证据2'])
    expect(refs[0].attributes('data-evidence-id')).toBe('planner-agent_ev_subtask_1_web_search_1')
    expect(wrapper.text()).not.toContain('planner-agent_ev_subtask_1_web_search_1')

    await refs[0].trigger('click')
    expect(wrapper.emitted('evidence-click')).toEqual([['planner-agent_ev_subtask_1_web_search_1']])
  })

  it('只链接当前 evidence_map 中存在的引用，未命中标记直接移除', async () => {
    const wrapper = mount(MarkdownRenderer, {
      props: {
        content: '已知 ev_subtask_1_web_search_1，未知 [evidence_id:ev_subtask_9_web_search_9]，变量 ev_handler.',
        evidenceMap: [{ evidence_id: 'ev_subtask_1_web_search_1' }],
        evidenceLabel: 'evidence'
      }
    })

    await nextTick()

    // 命中引用只有一个：整段被 promote 为可点击正文（evidence-ref 被移除）
    const linkedContent = wrapper.find('.evidence-linked-content')
    expect(linkedContent.exists()).toBe(true)
    expect(linkedContent.attributes('data-evidence-id')).toBe('ev_subtask_1_web_search_1')
    // 未命中的显式标记直接移除：不回显原始 evidence_id，也不渲染占位标签
    expect(wrapper.find('.evidence-ref-unknown').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('[evidence_id:')
    expect(wrapper.text()).not.toContain('ev_subtask_9_web_search_9')
    expect(wrapper.text()).toContain('ev_handler')

    await linkedContent.trigger('click')
    expect(wrapper.emitted('evidence-click')).toEqual([['ev_subtask_1_web_search_1']])
  })

  it('行内代码中照抄的 [evidence_id:...] 标记同样收敛为短标签', async () => {
    const wrapper = mount(MarkdownRenderer, {
      props: {
        content: '引用写成行内代码 `[evidence_id:lab_ev_subtask_1_llm_analysis_1]` 的场景。',
        evidenceMap: [{ evidence_id: 'lab_ev_subtask_1_llm_analysis_1', title: '来源' }],
        evidenceLabel: '证据'
      }
    })

    await nextTick()

    expect(wrapper.text()).not.toContain('evidence_id')
    expect(wrapper.text()).not.toContain('lab_ev_subtask_1_llm_analysis_1')
    // 段落内唯一引用被 promote 为可点击正文，引用标签移除
    const linkedContent = wrapper.find('.evidence-linked-content')
    expect(linkedContent.exists()).toBe(true)
    expect(linkedContent.attributes('data-evidence-id')).toBe('lab_ev_subtask_1_llm_analysis_1')

    await linkedContent.trigger('click')
    expect(wrapper.emitted('evidence-click')).toEqual([['lab_ev_subtask_1_llm_analysis_1']])
  })

  it('显示已转义的大于号和小于号实体', async () => {
    const wrapper = mount(MarkdownRenderer, {
      props: {
        content: '判断条件：A &gt; B 且 C &lt; D，文本标签 &lt;safe&gt; 保持为文本。'
      }
    })

    await nextTick()

    expect(wrapper.text()).toContain('A > B')
    expect(wrapper.text()).toContain('C < D')
    expect(wrapper.text()).toContain('<safe>')
    expect(wrapper.text()).not.toContain('&gt;')
    expect(wrapper.text()).not.toContain('&lt;')
  })
})
