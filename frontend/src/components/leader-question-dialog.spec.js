import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'
import LeaderQuestionDialog from './LeaderQuestionDialog.vue'
import { useLeaderStore } from '@/stores/leader'
import { i18n } from '@/locales'

const DialogStub = {
  props: ['modelValue'],
  emits: ['update:modelValue', 'close'],
  template: '<div v-if="modelValue" class="dialog-stub"><slot /><slot name="footer" /></div>'
}

describe('LeaderQuestionDialog', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('页面重新获得焦点时重新显示同一轮追问', async () => {
    const store = useLeaderStore()
    store.leaderState = 'questioning'
    store.currentQuestions = [{ question: '目标平台是什么？', options: ['Web', '桌面端'] }]

    const wrapper = mount(LeaderQuestionDialog, {
      global: {
        stubs: {
          'el-dialog': DialogStub,
          'el-alert': true,
          'el-checkbox-group': true,
          'el-checkbox': true,
          'el-radio-group': true,
          'el-radio': true,
          'el-input': true,
          'el-button': true
        }
      }
    })

    expect(wrapper.find('.dialog-stub').exists()).toBe(true)

    wrapper.findComponent(DialogStub).vm.$emit('update:modelValue', false)
    await nextTick()
    expect(wrapper.find('.dialog-stub').exists()).toBe(false)

    window.dispatchEvent(new Event('focus'))
    await nextTick()
    expect(wrapper.find('.dialog-stub').exists()).toBe(true)

    wrapper.unmount()
  })

  it('组件挂载后首次收到追问时立即显示弹窗', async () => {
    const store = useLeaderStore()
    const wrapper = mount(LeaderQuestionDialog, {
      global: {
        stubs: {
          'el-dialog': DialogStub,
          'el-alert': true,
          'el-checkbox-group': true,
          'el-checkbox': true,
          'el-radio-group': true,
          'el-radio': true,
          'el-input': true,
          'el-button': true
        }
      }
    })

    expect(wrapper.find('.dialog-stub').exists()).toBe(false)

    store.currentQuestions = [{
      question: 'Which deployment target should the plan use?',
      options: ['Existing cluster', 'New cluster']
    }]
    store.leaderState = 'questioning'
    await nextTick()

    expect(wrapper.find('.dialog-stub').exists()).toBe(true)
    expect(wrapper.text()).toContain('Which deployment target should the plan use?')

    wrapper.unmount()
  })

  it('英文结构化多选按 multiple 渲染并使用英文分隔符提交', async () => {
    i18n.global.locale.value = 'zh-CN'
    const store = useLeaderStore()
    store.submitAnswers = async answers => {
      expect(answers).toEqual(['Existing cluster, New cluster'])
      store.leaderState = 'completed'
    }
    store.currentQuestions = [{
      question: 'Which targets are acceptable?',
      options: ['Existing cluster', 'New cluster', 'Managed service'],
      selection_type: 'multiple',
      content_locale: 'en-US'
    }]
    store.leaderState = 'questioning'

    const wrapper = mount(LeaderQuestionDialog, {
      global: {
        stubs: {
          'el-dialog': DialogStub,
          'el-alert': true,
          'el-checkbox-group': {
            template: '<div class="checkbox-group"><slot /></div>'
          },
          'el-checkbox': true,
          'el-radio-group': true,
          'el-radio': true,
          'el-input': true,
          'el-button': true
        }
      }
    })
    await nextTick()

    expect(wrapper.find('.checkbox-group').exists()).toBe(true)
    const setup = wrapper.vm.$.setupState
    setup.answers[0].selectedList = ['Existing cluster', 'New cluster']
    await setup.handleSubmit()

    wrapper.unmount()
  })

  it('兼容英文旧问题中的 select all that apply 标记', async () => {
    const store = useLeaderStore()
    store.currentQuestions = [{
      question: 'Select all that apply',
      options: ['A', 'B', 'C']
    }]
    store.leaderState = 'questioning'

    const wrapper = mount(LeaderQuestionDialog, {
      global: {
        stubs: {
          'el-dialog': DialogStub,
          'el-alert': true,
          'el-checkbox-group': {
            template: '<div class="checkbox-group"><slot /></div>'
          },
          'el-checkbox': true,
          'el-radio-group': true,
          'el-radio': true,
          'el-input': true,
          'el-button': true
        }
      }
    })
    await nextTick()

    expect(wrapper.find('.checkbox-group').exists()).toBe(true)
    wrapper.unmount()
  })
})
