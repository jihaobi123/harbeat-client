import { useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { BrandIllustration } from '../components/editorial/BrandIllustration'
import { EditorialKicker } from '../components/editorial/EditorialPrimitives'

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
    <main className="auth-page street-theme">
      <section className="auth-page__hero" aria-labelledby="auth-brand-title">
        <EditorialKicker number="01">HarBeat / Personal</EditorialKicker>
        <h1 id="auth-brand-title">YOUR BEAT.<br />YOUR MARK.</h1>
        <p>hiphop street music platform</p>
        <BrandIllustration variant="turntable" />
      </section>

      <form onSubmit={handleSubmit} className="auth-page__form street-sticker space-y-4">
        <EditorialKicker number="02">{isRegister ? 'Register / 注册' : 'Login / 登录'}</EditorialKicker>
        <h2 className="street-title">
          {isRegister ? 'CREATE YOUR PROFILE.' : 'STEP INTO THE BEAT.'}
        </h2>

        {error && (
          <div className="editorial-state editorial-state--error text-sm" role="alert">
            {error}
          </div>
        )}

        <div>
          <label className="block text-sm mb-1 street-subtitle" htmlFor="username">USERNAME</label>
          <input
            id="username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-4 py-2.5"
            placeholder="your username"
            autoComplete="username"
          />
        </div>

        <div>
          <label className="block text-sm mb-1 street-subtitle" htmlFor="password">PASSWORD</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-4 py-2.5"
            placeholder="your password"
            autoComplete={isRegister ? 'new-password' : 'current-password'}
          />
        </div>

        {isRegister && (
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm mb-1 street-subtitle" htmlFor="dance-style">STYLE</label>
              <select
                id="dance-style"
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
              <label className="block text-sm mb-1 street-subtitle" htmlFor="dance-level">LEVEL</label>
              <select
                id="dance-level"
                value={level}
                onChange={(e) => setLevel(e.target.value)}
                className="w-full px-4 py-2.5"
              >
                <option value="beginner">beginner</option>
                <option value="intermediate">intermediate</option>
                <option value="advanced">advanced</option>
              </select>
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-primary disabled:opacity-50 font-bold py-2.5"
        >
          {loading ? 'PROCESSING...' : isRegister ? 'REGISTER →' : 'LOGIN →'}
        </button>

        <p className="text-center text-sm">
          {isRegister ? 'Already have account?' : 'No account yet?'}
          <button
            type="button"
            className="ml-2 px-3 py-1 bg-surface-lighter text-sm"
            onClick={() => { setIsRegister(!isRegister); setError('') }}
          >
            {isRegister ? 'LOGIN' : 'REGISTER'}
          </button>
        </p>
      </form>
    </main>
  )
}
