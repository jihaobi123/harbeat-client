import React, { useEffect, useRef } from 'react'
import { Search, X, Loader2 } from 'lucide-react'
import { useMusicStore } from '../store/useMusicStore'

export const SearchBar: React.FC = () => {
  const searchQuery = useMusicStore((s) => s.searchQuery)
  const setSearchQuery = useMusicStore((s) => s.setSearchQuery)
  const currentView = useMusicStore((s) => s.currentView)
  const searchPlatform = useMusicStore((s) => s.searchPlatform)
  const platformSearchLoading = useMusicStore((s) => s.platformSearchLoading)
  const isPlatform = currentView === 'platform'
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debounced platform search when in platform view
  useEffect(() => {
    if (!isPlatform) return
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      searchPlatform(searchQuery)
    }, 500)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [searchQuery, isPlatform, searchPlatform])

  // Load local songs into platform when switching to platform view with empty query
  useEffect(() => {
    if (isPlatform && !searchQuery) {
      searchPlatform('')
    }
  }, [isPlatform])

  return (
    <div className="relative">
      {platformSearchLoading && isPlatform ? (
        <Loader2
          size={15}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-primary animate-spin"
        />
      ) : (
        <Search
          size={15}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
        />
      )}
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder={isPlatform ? '搜索平台曲库 / fangpi.net...' : '搜索歌曲名或艺术家...'}
        className="w-full bg-surface-dark border border-border rounded-lg pl-9 pr-8 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20 transition-all"
      />
      {searchQuery && (
        <button
          onClick={() => setSearchQuery('')}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white transition-colors"
        >
          <X size={14} />
        </button>
      )}
    </div>
  )
}
