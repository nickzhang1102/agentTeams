import axios from 'axios'
import { ElMessage } from 'element-plus'
import { getCurrentLocale } from '@/locales'

// 创建 axios 实例
const api = axios.create({
  baseURL: '',
  timeout: 30000,
  withCredentials: true  // 自动携带 httpOnly cookie
})

// 请求拦截器：httpOnly cookie 自动携带，不再手动添加 Authorization header
api.interceptors.request.use(
  config => {
    // cookie 由浏览器自动附加（withCredentials: true）
    // 保留 localStorage token 作为 fallback（向后兼容，可逐步移除）
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    config.headers['Accept-Language'] = getCurrentLocale()
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  response => {
    return response
  },
  error => {
    if (error.config?.suppressGlobalError) {
      return Promise.reject(error)
    }

    if (error.response) {
      switch (error.response.status) {
        case 401:
          // 登录接口的 401 是正常业务错误，不触发全局跳转
          if (error.config?.url?.includes('/api/auth/login')) {
            break
          }
          // 未授权,清除 token 并跳转到登录页
          localStorage.removeItem('token')
          localStorage.removeItem('user')
          window.location.href = '/login'
          ElMessage.error('登录已过期,请重新登录')
          break
        case 403:
          ElMessage.error('没有权限访问')
          break
        case 404:
          ElMessage.error('请求的资源不存在')
          break
        case 500:
          ElMessage.error('服务器错误')
          break
        default:
          ElMessage.error(error.response.data?.error || error.response.data?.detail?.error || '请求失败')
      }
    } else if (error.request) {
      ElMessage.error('网络错误,请检查网络连接')
    } else {
      ElMessage.error('请求配置错误')
    }
    return Promise.reject(error)
  }
)

export default api
