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
    set({ loading: true, error: null })
    try {
      const res = await login(username, password)
      setToken(res.access_token)
      const me = await getMe()
      set({ user: me as User, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
      throw e
    }
  },

  doRegister: async (username, password, dance_style = 'hiphop', level = 'beginner', favorite_style = 'hiphop') => {
    set({ loading: true, error: null })
    try {
      const res = await register({ username, password, dance_style, level, favorite_style })
      setToken(res.access_token)
      const me = await getMe()
      set({ user: me as User, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
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
