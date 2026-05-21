import { create } from 'zustand'
import type { User } from '../types'
import { clearToken, getMe, login, register, setToken } from '../api/client'

interface AuthState {
  user: User | null
  loading: boolean
  error: string | null

  doLogin: (username: string, password: string) => Promise<void>
  doRegister: (username: string, password: string, danceStyle?: string, level?: string, favoriteStyle?: string) => Promise<void>
  doLogout: () => void
  checkAuth: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  error: null,

  doLogin: async (username, password) => {
    set({ error: null })
    try {
      const res = await login(username, password)
      setToken(res.access_token)
      // Use token response data directly, then try to enrich with getMe
      const user: User = { id: res.user_id, username: res.username, dance_style: '', level: '', favorite_style: '' }
      try {
        const me = await getMe()
        set({ user: me as User, loading: false })
      } catch {
        set({ user, loading: false })
      }
    } catch (e: any) {
      set({ error: e.message })
      throw e
    }
  },

  doRegister: async (username, password, dance_style = 'hiphop', level = 'beginner', favorite_style = 'hiphop') => {
    set({ error: null })
    try {
      const res = await register({ username, password, dance_style, level, favorite_style })
      setToken(res.access_token)
      // Set user immediately from known data, don't depend on getMe
      const user: User = { id: res.user_id, username: res.username, dance_style, level, favorite_style }
      set({ user, loading: false })
    } catch (e: any) {
      set({ error: e.message })
      throw e
    }
  },

  doLogout: () => {
    clearToken()
    set({ user: null, loading: false, error: null })
  },

  checkAuth: async () => {
    const token = localStorage.getItem('harbeat_token')
    if (!token) {
      set({ loading: false })
      return
    }
    try {
      const me = await getMe()
      set({ user: me as User, loading: false })
    } catch {
      clearToken()
      set({ user: null, loading: false })
    }
  },
}))
