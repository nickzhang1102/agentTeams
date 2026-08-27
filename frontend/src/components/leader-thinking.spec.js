import { beforeEach, describe, expect, it } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { useLeaderStore } from '@/stores/leader'
import LeaderThinking from './LeaderThinking.vue'

describe('LeaderThinking embed history updates', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders Leader messages written after the component has mounted', async () => {
    const store = useLeaderStore()
    const wrapper = shallowMount(LeaderThinking, {
      props: { sessionId: 77 },
      global: {
        stubs: {
          MarkdownRenderer: {
            props: ['content'],
            template: '<div class="markdown-stub">{{ content }}</div>',
          },
          ContentTranslationStatus: true,
          'el-icon': true,
          'el-empty': true,
        },
      },
    })

    expect(wrapper.findAll('.message-item')).toHaveLength(0)

    store.historicalMessages = [{
      id: 9,
      type: 'assessment',
      leader_session_id: 77,
      rawContent: 'Leader 已完成需求评估',
      content: 'Leader 已完成需求评估',
      time: '09:30',
    }]
    await nextTick()

    expect(wrapper.findAll('.message-item')).toHaveLength(1)
    expect(wrapper.text()).toContain('Leader 已完成需求评估')
  })

  it('renders live Leader messages without dropping persisted history', async () => {
    const store = useLeaderStore()
    store.historicalMessages = [{
      id: 9,
      type: 'assessment',
      leader_session_id: 77,
      content: '持久化评估',
      time: '09:30',
    }]
    const wrapper = shallowMount(LeaderThinking, {
      props: { sessionId: '77' },
      global: {
        stubs: {
          MarkdownRenderer: {
            props: ['content'],
            template: '<div class="markdown-stub">{{ content }}</div>',
          },
          ContentTranslationStatus: true,
          'el-icon': true,
          'el-empty': true,
        },
      },
    })

    store.messages.push({
      id: 'sse-live-team-ready',
      type: 'progress',
      leader_session_id: 77,
      content: '实时组队完成',
      created_at: '2026-08-11T09:31:00Z',
    })
    await nextTick()

    expect(wrapper.text()).toContain('持久化评估')
    expect(wrapper.text()).toContain('实时组队完成')
  })

  it('does not render the original consultation prompt as a Leader message', async () => {
    const store = useLeaderStore()
    store.historicalMessages = [{
      id: 8,
      type: 'user',
      leader_session_id: 77,
      content: '完整会诊提示词不应显示在 Leader 消息中',
      time: '09:29',
    }, {
      id: 9,
      type: 'assessment',
      leader_session_id: 77,
      content: 'Leader 已完成需求评估',
      time: '09:30',
    }]

    const wrapper = shallowMount(LeaderThinking, {
      props: { sessionId: 77 },
      global: {
        stubs: {
          MarkdownRenderer: {
            props: ['content'],
            template: '<div class="markdown-stub">{{ content }}</div>',
          },
          ContentTranslationStatus: true,
          'el-icon': true,
          'el-empty': true,
        },
      },
    })
    await nextTick()

    expect(wrapper.text()).not.toContain('完整会诊提示词')
    expect(wrapper.text()).toContain('Leader 已完成需求评估')
  })

  it('does not render its own stop action (handled by ConversationDisplay header)', async () => {
    const store = useLeaderStore()
    store.leaderState = 'monitoring'

    const wrapper = shallowMount(LeaderThinking, {
      props: { sessionId: 77, allowStop: true },
      global: {
        stubs: {
          MarkdownRenderer: true,
          ContentTranslationStatus: true,
          'el-icon': true,
          'el-empty': true,
          'el-button': true,
        },
      },
    })
    await nextTick()

    expect(wrapper.find('.stop-bar').exists()).toBe(false)
  })
})
