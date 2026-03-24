import React, { useState } from 'react'
import { Loader2, Music } from 'lucide-react'
import { useAuthStore } from '../store/useAuthStore'

export const LoginPage: React.FC = () => {
  const login = useAuthStore((s) => s.login)
  const loading = useAuthStore((s) => s.loading)
  const error = useAuthStore((s) => s.error)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) return
    await login(username.trim(), password.trim())
  }

  return (
    <div className="flex h-screen bg-background items-center justify-center">
      <div className="w-[380px] bg-surface rounded-xl border border-border shadow-2xl p-8">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-primary/20 flex items-center justify-center mb-3">
            <Music size={28} className="text-primary" />
          </div>
          <h1 className="text-xl font-bold text-white">Harbeat</h1>
          <p className="text-xs text-slate-500 mt-1">街舞音乐管理平台</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1.5">用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
              autoFocus
              className="w-full bg-surface-dark border border-border rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-primary transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1.5">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
              className="w-full bg-surface-dark border border-border rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-primary transition-colors"
            />
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading || !username.trim() || !password.trim()}
            className="w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover disabled:opacity-40 disabled:cursor-not-allowed text-white py-2.5 rounded-lg text-sm font-medium transition-all mt-2"
          >
            {loading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                登录中...
              </>
            ) : (
              '登 录'
            )}
          </button>
        </form>

        <p className="text-[10px] text-slate-600 text-center mt-6">
          还没有账号？请联系管理员开通
        </p>
      </div>
    </div>
  )
}
