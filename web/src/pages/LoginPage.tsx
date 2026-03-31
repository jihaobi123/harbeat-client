import { useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'

export default function LoginPage() {
  const [isRegister, setIsRegister] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [danceStyle, setDanceStyle] = useState('hiphop')
  const [level, setLevel] = useState('beginner')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { doLogin, doRegister } = useAuthStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) {
      setError('请填写用户名和密码')
      return
    }
    setError('')
    setLoading(true)
    try {
      if (isRegister) {
        await doRegister(username.trim(), password, danceStyle, level, danceStyle)
      } else {
        await doLogin(username.trim(), password)
      }
    } catch (err: any) {
      setError(err.message || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">🎵 HarBeat</h1>
          <p className="text-gray-400">街舞音乐管理平台</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-surface-light rounded-2xl p-8 shadow-lg space-y-5">
          <h2 className="text-xl font-semibold text-white text-center">
            {isRegister ? '注册账号' : '登录'}
          </h2>

          {error && (
            <div className="bg-red-500/20 border border-red-500/40 rounded-lg px-4 py-2 text-red-300 text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm text-gray-400 mb-1">用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-surface rounded-lg px-4 py-2.5 text-white border border-gray-600 focus:border-primary focus:outline-none"
              placeholder="输入用户名"
              autoComplete="username"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-surface rounded-lg px-4 py-2.5 text-white border border-gray-600 focus:border-primary focus:outline-none"
              placeholder="输入密码"
              autoComplete={isRegister ? 'new-password' : 'current-password'}
            />
          </div>

          {isRegister && (
            <>
              <div>
                <label className="block text-sm text-gray-400 mb-1">舞蹈风格</label>
                <select
                  value={danceStyle}
                  onChange={(e) => setDanceStyle(e.target.value)}
                  className="w-full bg-surface rounded-lg px-4 py-2.5 text-white border border-gray-600 focus:border-primary focus:outline-none"
                >
                  {['hiphop','jazz','breaking','popping','locking','waacking','house','krump','other'].map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">水平</label>
                <select
                  value={level}
                  onChange={(e) => setLevel(e.target.value)}
                  className="w-full bg-surface rounded-lg px-4 py-2.5 text-white border border-gray-600 focus:border-primary focus:outline-none"
                >
                  <option value="beginner">初学者</option>
                  <option value="intermediate">中级</option>
                  <option value="advanced">高级</option>
                </select>
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-primary hover:bg-primary-dark disabled:opacity-50 text-white font-semibold rounded-lg py-2.5 transition"
          >
            {loading ? '请稍候...' : isRegister ? '注册' : '登录'}
          </button>

          <p className="text-center text-sm text-gray-400">
            {isRegister ? '已有账号？' : '没有账号？'}
            <button
              type="button"
              className="text-primary hover:underline ml-1"
              onClick={() => { setIsRegister(!isRegister); setError('') }}
            >
              {isRegister ? '去登录' : '注册'}
            </button>
          </p>
        </form>
      </div>
    </div>
  )
}
