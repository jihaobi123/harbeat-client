import { create } from 'zustand'
import type { User } from '../types'
import { login as apiLogin, getUserInfo } from '../services/api'

interface AuthStore {
  user: User | null
  loading: boolean
  error: string | null

  login: (username: string, password: string) => Promise<boolean>
  logout: () => void
  loadUser: () => void
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  loading: false,
  error: null,

  login: async (username: string, password: string) => {
    set({ loading: true, error: null })
    try {
      const res = await apiLogin({ username, password })
      if (res.code === 0 && res.data) {
        const user: User = {
          ...res.data.user,
          token: res.data.token,
        }
        localStorage.setItem('harbeat_user', JSON.stringify(user))
        set({ user, loading: false, error: null })
        return true
      } else {
        set({ loading: false, error: res.message || '登录失败' })
        return false
      }
    } catch (e) {
      set({ loading: false, error: String(e) })
      return false
    }
  },

  logout: () => {
    localStorage.removeItem('harbeat_user')
    set({ user: null, error: null })
  },

  loadUser: () => {
    try {
      const stored = localStorage.getItem('harbeat_user')
      if (stored) {
        const user = JSON.parse(stored) as User
        set({ user })
        // 有后端 API 时才校验 token
        if (import.meta.env.VITE_API_BASE_URL) {
          getUserInfo().catch(() => {
            localStorage.removeItem('harbeat_user')
            set({ user: null })
          })
        }
      }
    } catch { /* ignore */ }
  },
}))
