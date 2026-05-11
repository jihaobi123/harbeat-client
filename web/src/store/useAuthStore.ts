import { create } from 'zustand';
import { authApi } from '../api/auth';

interface AuthState {
  token: string | null;
  userId: number | null;
  username: string | null;
  isAuthenticated: boolean;
  loading: boolean;
  error: string | null;

  login: (username: string, password: string) => Promise<boolean>;
  register: (username: string, password: string, danceStyle?: string) => Promise<boolean>;
  logout: () => void;
  checkAuth: () => Promise<boolean>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('harbeat_token'),
  userId: null,
  username: null,
  isAuthenticated: false,
  loading: false,
  error: null,

  login: async (username, password) => {
    set({ loading: true, error: null });
    try {
      const res = await authApi.login({ username, password });
      const { access_token, user_id, username: uname } = res.data.data;
      localStorage.setItem('harbeat_token', access_token);
      set({
        token: access_token,
        userId: user_id,
        username: uname,
        isAuthenticated: true,
        loading: false,
      });
      return true;
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Login failed';
      set({ loading: false, error: msg });
      return false;
    }
  },

  register: async (username, password, danceStyle) => {
    set({ loading: true, error: null });
    try {
      const res = await authApi.register({ username, password, dance_style: danceStyle });
      const { access_token, user_id, username: uname } = res.data.data;
      localStorage.setItem('harbeat_token', access_token);
      set({
        token: access_token,
        userId: user_id,
        username: uname,
        isAuthenticated: true,
        loading: false,
      });
      return true;
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Registration failed';
      set({ loading: false, error: msg });
      return false;
    }
  },

  logout: () => {
    localStorage.removeItem('harbeat_token');
    set({
      token: null,
      userId: null,
      username: null,
      isAuthenticated: false,
    });
  },

  checkAuth: async () => {
    const token = localStorage.getItem('harbeat_token');
    if (!token) return false;
    try {
      const res = await authApi.me();
      set({
        token,
        userId: res.data.data.user_id,
        username: res.data.data.username,
        isAuthenticated: true,
      });
      return true;
    } catch {
      localStorage.removeItem('harbeat_token');
      set({ token: null, isAuthenticated: false });
      return false;
    }
  },

  clearError: () => set({ error: null }),
}));
