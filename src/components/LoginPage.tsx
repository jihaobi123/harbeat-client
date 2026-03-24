import React, { useState } from 'react'
import { Loader2, Music } from 'lucide-react'

import { useAuthStore } from '../store/useAuthStore'

const DANCE_STYLES = [
  'hiphop',
  'jazz',
  'breaking',
  'popping',
  'locking',
  'waacking',
  'house',
  'krump',
]

const LEVELS = ['beginner', 'intermediate', 'advanced']

export const LoginPage: React.FC = () => {
  const initialize = useAuthStore((state) => state.initialize)
  const loading = useAuthStore((state) => state.loading)
  const error = useAuthStore((state) => state.error)

  const [username, setUsername] = useState('')
  const [danceStyle, setDanceStyle] = useState('hiphop')
  const [level, setLevel] = useState('beginner')
  const [favoriteStyle, setFavoriteStyle] = useState('hiphop')

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!username.trim()) return

    await initialize({
      username: username.trim(),
      dance_style: danceStyle,
      level,
      favorite_style: favoriteStyle,
    })
  }

  return (
    <div className="flex h-screen bg-background items-center justify-center">
      <div className="w-[420px] bg-surface rounded-xl border border-border shadow-2xl p-8">
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-primary/20 flex items-center justify-center mb-3">
            <Music size={28} className="text-primary" />
          </div>
          <h1 className="text-xl font-bold text-white">Harbeat</h1>
          <p className="text-xs text-slate-500 mt-1">User setup and unified entry</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1.5">Username</label>
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Enter username"
              autoFocus
              className="w-full bg-surface-dark border border-border rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-primary transition-colors"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Dance Style</label>
              <select
                value={danceStyle}
                onChange={(event) => setDanceStyle(event.target.value)}
                className="w-full bg-surface-dark border border-border rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-primary transition-colors"
              >
                {DANCE_STYLES.map((style) => (
                  <option key={style} value={style}>
                    {style}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Level</label>
              <select
                value={level}
                onChange={(event) => setLevel(event.target.value)}
                className="w-full bg-surface-dark border border-border rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-primary transition-colors"
              >
                {LEVELS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1.5">Favorite Style</label>
            <select
              value={favoriteStyle}
              onChange={(event) => setFavoriteStyle(event.target.value)}
              className="w-full bg-surface-dark border border-border rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-primary transition-colors"
            >
              {DANCE_STYLES.map((style) => (
                <option key={style} value={style}>
                  {style}
                </option>
              ))}
            </select>
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading || !username.trim()}
            className="w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover disabled:opacity-40 disabled:cursor-not-allowed text-white py-2.5 rounded-lg text-sm font-medium transition-all mt-2"
          >
            {loading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Initializing...
              </>
            ) : (
              'Enter Workspace'
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
