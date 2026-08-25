import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Register.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: () => import('@/views/KnowledgePage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/agents',
    name: 'Agents',
    component: () => import('@/views/AgentsPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/templates',
    name: 'WorkflowTemplates',
    component: () => import('@/views/WorkflowTemplatesPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/conversation/:token',
    name: 'ConversationDisplay',
    component: () => import('@/views/ConversationDisplay.vue'),
    meta: { requiresAuth: false },  // 公开访问，无需登录
    props: true
  },
  {
    path: '/project/settings',
    name: 'ProjectSettings',
    component: () => import('@/views/ProjectSettings.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/embed/conversation/:token',
    name: 'AgentTeamsEmbedConversation',
    component: () => import('@/views/ConversationDisplay.vue'),
    meta: { requiresAuth: false },
    props: route => ({
      token: route.params.token,
      accessMode: 'embed'
    })
  },
  // 带侧边栏的聊天布局
  {
    path: '/chat',
    component: () => import('@/views/ChatLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'ChatHome',
        component: () => import('@/views/Home.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: ':token',
        name: 'ChatConversation',
        component: () => import('@/views/ConversationDisplay.vue'),
        meta: { requiresAuth: true },
        props: true
      }
    ]
  },
  // 管理后台：嵌套路由结构，Layout 组件负责权限校验
  {
    path: '/admin',
    component: () => import('@/views/admin/Layout.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
    redirect: '/admin/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'AdminDashboard',
        component: () => import('@/views/admin/Dashboard.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'performance',
        name: 'AdminPerformance',
        component: () => import('@/views/admin/Performance.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'leader-sessions',
        name: 'AdminLeaderSessions',
        component: () => import('@/views/admin/LeaderSessions.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'featured',
        name: 'AdminFeatured',
        component: () => import('@/views/admin/Featured.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'tools',
        name: 'AdminTools',
        component: () => import('@/views/admin/Tools.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'openharness',
        name: 'AdminOpenHarness',
        component: () => import('@/views/admin/OpenHarness.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'agentteams-integration',
        name: 'AdminAgentTeamsIntegration',
        component: () => import('@/views/admin/AgentTeamsIntegration.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'llm-models',
        name: 'AdminLLMModels',
        redirect: '/project/settings',
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'settings',
        name: 'AdminSettings',
        redirect: '/project/settings',
        meta: { requiresAuth: true, requiresAdmin: true }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫（带短暂缓存，避免每次跳转都探测 /api/auth/me）
let _authCache = { result: null, ts: 0 }
const AUTH_CACHE_TTL = 5000 // 5 秒缓存

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // 如果需要认证
  if (to.meta.requiresAuth) {
    // 短缓存：同一 TTL 内复用上次探测结果，减少 RTT
    const now = Date.now()
    let authed
    if (now - _authCache.ts < AUTH_CACHE_TTL) {
      authed = _authCache.result
    } else {
      authed = await authStore.checkAuth()
      _authCache = { result: authed, ts: now }
    }

    if (!authed) {
      next('/login')
      return
    }

    // 管理员页面权限校验
    if (to.meta.requiresAdmin && !authStore.user?.is_admin) {
      next('/')
      return
    }
  }

  // 如果访问登录/注册页但已登录，跳转到首页
  if ((to.path === '/login' || to.path === '/register') && authStore.isAuthenticated) {
    next('/')
    return
  }

  next()
})

export default router
