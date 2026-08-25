import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import { i18n } from './locales'
import { useLocaleStore } from './stores/locale'
import './styles/design-system.scss'
import './styles/dark-mode.scss'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(i18n)
await useLocaleStore(pinia).initializeLocale()
app.use(router)
app.use(ElementPlus)

app.mount('#app')
