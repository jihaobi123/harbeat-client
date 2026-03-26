import { create } from 'zustand'

import type { User } from '../types'
import { getUserInfo, initializeUser, type InitializeUserRequest } from '../services/api'

interface AuthStore {
  user: User | null
  loading: boolean
  error: string | null
  initialize: (payload: InitializeUserRequest) => Promise<boolean>
  logout: () => void
  loadUser: () => Promise<void>
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  loading: false,
  error: null,

  initialize: async (payload) => {
    set({ loading: true, error: null })
    try {
      const response = await initializeUser(payload)
      if (response.code === 0 && response.data) {
        localStorage.setItem('harbeat_user', JSON.stringify(response.data))
        set({ user: response.data, loading: false, error: null })
        return true
      }
      set({ loading: false, error: response.message || 'user initialization failed' })
      return false
    } catch (error) {
      set({ loading: false, error: String(error) })
      return false
    }
  },

  logout: () => {
    localStorage.removeItem('harbeat_user')
    set({ user: null, error: null })
  },

  loadUser: async () => {
    try {
      const stored = localStorage.getItem('harbeat_user')
      if (!stored) return
      const cached = JSON.parse(stored) as User
      // Validate that cached id is a numeric string (backend expects int)
      if (!cached.id || isNaN(Number(cached.id))) {
        localStorage.removeItem('harbeat_user')
        set({ user: null })
        return
      }
      const fresh = await getUserInfo(cached.id)
      if (fresh.data) {
        localStorage.setItem('harbeat_user', JSON.stringify(fresh.data))
        set({ user: fresh.data, error: null })
      } else {
        set({ user: cached })
      }
    } catch {
      const stored = localStorage.getItem('harbeat_user')
      if (!stored) return
      try {
        set({ user: JSON.parse(stored) as User })
      } catch {
        localStorage.removeItem('harbeat_user')
        set({ user: null })
      }
    }
  },
}))
