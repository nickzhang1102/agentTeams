// 测试全局设置
import { config } from '@vue/test-utils'
import { i18n } from '@/locales'

// 禁用 Vue 警告
config.global.warnHandler = () => null
config.global.plugins = [i18n]
