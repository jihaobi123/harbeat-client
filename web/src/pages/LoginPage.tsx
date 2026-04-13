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
      setError('Please input username and password')
      return
    }
    if (isRegister && password.length < 8) {
      setError('Password must be at least 8 characters')
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
      setError(err.message || 'Action failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4 street-theme">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <h1 className="text-4xl sm:text-5xl street-title mb-2">HarBeat</h1>
          <p className="street-subtitle text-sm">hiphop street music platform</p>
        </div>

        <form onSubmit={handleSubmit} className="street-sticker p-5 sm:p-7 space-y-4 bg-surface-light">
          <h2 className="text-3xl street-title text-center">
            {isRegister ? 'REGISTER' : 'LOGIN'}
          </h2>

          {error && (
            <div className="bg-red-500/20 border border-red-500/40 rounded-lg px-4 py-2 text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm mb-1 street-subtitle">USERNAME</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-2.5"
              placeholder="your username"
              autoComplete="username"
            />
          </div>

          <div>
            <label className="block text-sm mb-1 street-subtitle">PASSWORD</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2.5"
              placeholder="your password"
              autoComplete={isRegister ? 'new-password' : 'current-password'}
            />
          </div>

          {isRegister && (
            <>
              <div>
                <label className="block text-sm mb-1 street-subtitle">STYLE</label>
                <select
                  value={danceStyle}
                  onChange={(e) => setDanceStyle(e.target.value)}
                  className="w-full px-4 py-2.5"
                >
                  {['hiphop', 'jazz', 'breaking', 'popping', 'locking', 'waacking', 'house', 'krump', 'other'].map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm mb-1 street-subtitle">LEVEL</label>
                <select
                  value={level}
                  onChange={(e) => setLevel(e.target.value)}
                  className="w-full px-4 py-2.5"
                >
                  <option value="beginner">beginner</option>
                  <option value="intermediate">intermediate</option>
                  <option value="advanced">advanced</option>
                </select>
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-primary disabled:opacity-50 font-bold rounded-lg py-2.5"
          >
            {loading ? 'PROCESSING...' : isRegister ? 'REGISTER' : 'LOGIN'}
          </button>

          <p className="text-center text-sm">
            {isRegister ? 'Already have account?' : 'No account yet?'}
            <button
              type="button"
              className="ml-2 px-2 py-1 bg-surface-lighter text-sm"
              onClick={() => { setIsRegister(!isRegister); setError('') }}
            >
              {isRegister ? 'LOGIN' : 'REGISTER'}
            </button>
          </p>
        </form>
      </div>
    </div>
  )
}
