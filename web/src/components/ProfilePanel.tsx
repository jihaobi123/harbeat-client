import { useState, useEffect } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import * as api from '../api/client'
import type { UserProfile } from '../types'

export default function ProfilePanel() {
  const { user } = useAuthStore()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user) return
    setLoading(true)
    api.getProfile(user.id)
      .then(p => setProfile(p))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [user])

  const handleGenerate = async () => {
    if (!user) return
    setGenerating(true)
    setError('')
    try {
      const p = await api.generateProfile(user.id)
      setProfile(p)
    } catch (e: any) {
      setError(e.message || '生成失败')
    } finally {
      setGenerating(false)
    }
  }

  const profileItems = profile ? [
    { label: '偏好风格', value: profile.favorite_style, icon: '💃' },
    { label: '平均 BPM 偏好', value: profile.avg_bpm_preference ? `${profile.avg_bpm_preference} BPM` : '未知', icon: '🎵' },
    { label: '能量偏好', value: profile.energy_preference || '未知', icon: '⚡' },
    { label: '人声偏好', value: profile.vocal_preference || '未知', icon: '🎤' },
    { label: '年代偏好', value: profile.era_preference || '未知', icon: '📅' },
    { label: '律动偏好', value: profile.groove_preference || '未知', icon: '🎸' },
  ] : []

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-w-0">
      <div className="px-5 py-4 border-b border-gray-700">
        <h2 className="text-lg font-semibold text-white mb-1">👤 音乐画像</h2>
        <p className="text-xs text-gray-500">基于你的音乐库自动分析你的音乐品味</p>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* User info card */}
        <div className="bg-surface-light rounded-xl p-5">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 rounded-full bg-primary/30 flex items-center justify-center text-2xl">
              {user?.username?.[0]?.toUpperCase() || '?'}
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">{user?.username}</h3>
              <div className="text-sm text-gray-400">{user?.dance_style} · {user?.level}</div>
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={generating}
            className="bg-primary hover:bg-primary-dark disabled:opacity-50 text-white px-5 py-2 rounded-lg text-sm font-medium transition"
          >
            {generating ? '分析中...' : profile ? '🔄 重新生成画像' : '✨ 生成音乐画像'}
          </button>
        </div>

        {error && <div className="bg-red-500/20 border border-red-500/40 rounded-lg px-4 py-2 text-red-300 text-sm">{error}</div>}

        {loading && <div className="text-gray-500 text-sm text-center py-8">加载中...</div>}

        {/* Profile results */}
        {profile && !loading && (
          <div className="bg-surface-light rounded-xl p-5">
            <h3 className="text-sm font-semibold text-white mb-4">你的音乐品味画像</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {profileItems.map((item) => (
                <div key={item.label} className="bg-surface rounded-lg p-4 flex items-center gap-3">
                  <span className="text-2xl">{item.icon}</span>
                  <div>
                    <div className="text-xs text-gray-500">{item.label}</div>
                    <div className="text-sm text-white font-medium mt-0.5">{item.value}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {!profile && !loading && (
          <div className="text-center py-12">
            <div className="text-5xl mb-4">🎵</div>
            <p className="text-gray-400 text-sm">尚未生成音乐画像</p>
            <p className="text-gray-500 text-xs mt-1">上传音乐并导入歌单后，点击上方按钮生成</p>
          </div>
        )}
      </div>
    </div>
  )
}
