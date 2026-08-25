import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/utils/api'
import JSEncrypt from 'jsencrypt'
import { useLocaleStore } from '@/stores/locale'

const AUTH_ERROR_CODES = new Set([
  'PUBLIC_KEY_UNAVAILABLE',
  'PASSWORD_ENCRYPTION_FAILED',
  'PASSWORD_DECRYPTION_FAILED',
  'PASSWORD_TOO_COMMON',
  'PASSWORD_TOO_SHORT',
  'PASSWORD_COMPLEXITY',
  'USERNAME_EXISTS',
  'EMAIL_EXISTS',
  'INVALID_CREDENTIALS',
  'OLD_PASSWORD_INCORRECT',
  'PASSWORD_REUSED',
  'REGISTER_FAILED',
  'LOGIN_FAILED',
  'CHANGE_PASSWORD_FAILED',
  'REQUEST_FAILED',
])

function extractAuthError(error, fallbackCode = 'REQUEST_FAILED') {
  const data = error.response?.data
  const detail = data?.detail && typeof data.detail === 'object' ? data.detail : data
  const responseCode = detail?.code
  const code = AUTH_ERROR_CODES.has(responseCode) ? responseCode : fallbackCode
  return { code, error: detail?.error || data?.error || '' }
}

/**
 * 解码 JWT Token
 * @param {string} token - JWT token
 * @returns {object|null} 解码后的 payload
 */
function decodeToken(token) {
  if (!token) return null
  try {
    const base64Url = token.split('.')[1]
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    )
    return JSON.parse(jsonPayload)
  } catch (error) {
    console.error('Failed to decode token:', error)
    return null
  }
}

/**
 * 检查 Token 是否过期
 * @param {string} token - JWT token
 * @returns {boolean} 是否过期
 */
function isTokenExpired(token) {
  if (!token) return true
  try {
    const decoded = decodeToken(token)
    if (!decoded || !decoded.exp) return true
    // exp 是秒级时间戳，需要乘以 1000 转换为毫秒
    return decoded.exp * 1000 < Date.now()
  } catch {
    return true
  }
}

/**
 * 获取 RSA 公钥
 * @returns {Promise<string|null>} 公钥字符串
 */
async function getPublicKey() {
  try {
    const response = await api.get('/api/auth/public-key')
    return response.data.public_key
  } catch (error) {
    console.error('获取公钥失败:', error)
    return null
  }
}

/**
 * 使用 RSA 公钥加密密码
 * @param {string} password - 原始密码
 * @param {string} publicKey - RSA 公钥
 * @returns {string} Base64 编码的加密密码
 */
function encryptPassword(password, publicKey) {
  const encrypt = new JSEncrypt()
  encrypt.setPublicKey(publicKey)
  const encrypted = encrypt.encrypt(password)
  return encrypted
}

export const useAuthStore = defineStore('auth', () => {
  // token 存于 localStorage 作为前端状态判断与 Bearer 兼容层
  // 服务端同时下发 httpOnly Cookie(SameSite=Strict) 作为认证通道
  const token = ref(localStorage.getItem('token') || null)
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

  // computed：token 有效且未过期则为 true。checkAuth 探测到 401 时清除 token，自动变 false。
  const isAuthenticated = computed(() => !!token.value && !isTokenExpired(token.value))

  /**
   * 通过 /api/auth/me 探测实际认证状态
   * - 成功：isAuthenticated = true，同步 user 信息
   * - 401：isAuthenticated = false，清除 localStorage
   * @returns {Promise<boolean>} 是否已认证
   */
  async function checkAuth() {
    try {
      const response = await api.get('/api/auth/me')
      user.value = response.data
      localStorage.setItem('user', JSON.stringify(user.value))
      useLocaleStore().syncAuthenticatedUser(user.value)
      return true
    } catch (err) {
      // 401：cookie 确实过期/无效，清除前端状态
      if (err.response && err.response.status === 401) {
        token.value = null
        user.value = null
        localStorage.removeItem('token')
        localStorage.removeItem('user')
        useLocaleStore().clearAuthenticatedUser()
        return false
      }
      // 网络错误/服务端错误：保留现有状态，不误判为未登录
      // （isAuthenticated 仍由 computed 判断本地 token 有效性）
      return !!token.value && !isTokenExpired(token.value)
    }
  }

  async function login(username, password) {
    try {
      // 1. 获取公钥
      const publicKey = await getPublicKey()
      if (!publicKey) {
        return {
          success: false,
          code: 'PUBLIC_KEY_UNAVAILABLE'
        }
      }

      // 2. 加密密码
      const encryptedPassword = encryptPassword(password, publicKey)
      if (!encryptedPassword) {
        return {
          success: false,
          code: 'PASSWORD_ENCRYPTION_FAILED'
        }
      }

      // 3. 发送登录请求
      const response = await api.post('/api/auth/login', {
        username,
        password: encryptedPassword
      })

      token.value = response.data.access_token
      user.value = response.data.user

      // 存入 localStorage 作为前端状态判断（实际认证由 httpOnly cookie 承载）
      localStorage.setItem('token', token.value)
      localStorage.setItem('user', JSON.stringify(user.value))
      useLocaleStore().syncAuthenticatedUser(user.value)

      return { success: true }
    } catch (error) {
      return {
        success: false,
        ...extractAuthError(error, 'LOGIN_FAILED')
      }
    }
  }

  async function register(username, password, email) {
    try {
      // 1. 获取公钥
      const publicKey = await getPublicKey()
      if (!publicKey) {
        return {
          success: false,
          code: 'PUBLIC_KEY_UNAVAILABLE'
        }
      }

      // 2. 加密密码
      const encryptedPassword = encryptPassword(password, publicKey)
      if (!encryptedPassword) {
        return {
          success: false,
          code: 'PASSWORD_ENCRYPTION_FAILED'
        }
      }

      // 3. 发送注册请求
      const response = await api.post('/api/auth/register', {
        username,
        password: encryptedPassword,
        email
      })

      return { success: true, userId: response.data.user_id }
    } catch (error) {
      return {
        success: false,
        ...extractAuthError(error, 'REGISTER_FAILED')
      }
    }
  }

  async function fetchCurrentUser() {
    try {
      const response = await api.get('/api/auth/me')
      user.value = response.data
      localStorage.setItem('user', JSON.stringify(user.value))
      useLocaleStore().syncAuthenticatedUser(user.value)
      return { success: true }
    } catch (error) {
      console.error('[auth] fetchCurrentUser failed:', error)
      logout()
      return {
        success: false,
        ...extractAuthError(error)
      }
    }
  }

  /**
   * 修改密码
   * @param {string} oldPassword - 旧密码
   * @param {string} newPassword - 新密码
   * @returns {Promise<{success: boolean, error?: string}>}
   */
  async function changePassword(oldPassword, newPassword) {
    try {
      // 1. 获取公钥
      const publicKey = await getPublicKey()
      if (!publicKey) {
        return {
          success: false,
          code: 'PUBLIC_KEY_UNAVAILABLE'
        }
      }

      // 2. 加密密码
      const encryptedOldPassword = encryptPassword(oldPassword, publicKey)
      const encryptedNewPassword = encryptPassword(newPassword, publicKey)

      if (!encryptedOldPassword || !encryptedNewPassword) {
        return {
          success: false,
          code: 'PASSWORD_ENCRYPTION_FAILED'
        }
      }

      // 3. 发送修改密码请求
      await api.post('/api/auth/change-password', {
        old_password: encryptedOldPassword,
        new_password: encryptedNewPassword
      })

      return { success: true }
    } catch (error) {
      return {
        success: false,
        ...extractAuthError(error, 'CHANGE_PASSWORD_FAILED')
      }
    }
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    useLocaleStore().clearAuthenticatedUser()
  }

  /**
   * 检查并刷新 Token（如果即将过期）
   * @returns {Promise<{success: boolean}>}
   */
  async function checkAndRefreshToken() {
    if (!token.value) {
      return { success: false }
    }

    // 如果 Token 已过期，直接登出
    if (isTokenExpired(token.value)) {
      logout()
      return { success: false, reason: 'token_expired' }
    }

    // 检查是否即将过期（提前 5 分钟刷新）
    const decoded = decodeToken(token.value)
    if (decoded && decoded.exp) {
      const expiresAt = decoded.exp * 1000
      const now = Date.now()
      const fiveMinutes = 5 * 60 * 1000

      // 如果距离过期时间少于 5 分钟，尝试刷新
      if (expiresAt - now < fiveMinutes) {
        try {
          const response = await api.post('/api/auth/refresh')
          token.value = response.data.access_token
          localStorage.setItem('token', token.value)
          return { success: true, refreshed: true }
        } catch (error) {
          // 刷新失败，登出用户
          logout()
          return { success: false, reason: 'refresh_failed' }
        }
      }
    }

    return { success: true, refreshed: false }
  }

  return {
    token,
    user,
    isAuthenticated,
    login,
    register,
    fetchCurrentUser,
    logout,
    checkAuth,
    checkAndRefreshToken,
    changePassword
  }
})
