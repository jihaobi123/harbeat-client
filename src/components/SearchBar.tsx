import React, { useEffect, useRef } from 'react'
import { Loader2, Search, X } from 'lucide-react'

import { useMusicStore } from '../store/useMusicStore'

export const SearchBar: React.FC = () => {
  const searchQuery = useMusicStore((state) => state.searchQuery)
  const setSearchQuery = useMusicStore((state) => state.setSearchQuery)
  const currentView = useMusicStore((state) => state.currentView)
  const searchPlatform = useMusicStore((state) => state.searchPlatform)
  const platformSearchLoading = useMusicStore((state) => state.platformSearchLoading)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isPlatform = currentView === 'platform'

  useEffect(() => {
    if (!isPlatform) return
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      void searchPlatform(searchQuery)
    }, 400)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [isPlatform, searchPlatform, searchQuery])

  useEffect(() => {
    if (isPlatform && !searchQuery) {
      void searchPlatform('')
    }
  }, [isPlatform, searchPlatform, searchQuery])

  return (
    <div className="relative">
      {platformSearchLoading && isPlatform ? (
        <Loader2 size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-primary animate-spin" />
      ) : (
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
      )}
      <input
        type="text"
        value={searchQuery}
        onChange={(event) => setSearchQuery(event.target.value)}
        placeholder={isPlatform ? 'Search platform music...' : 'Search songs or artists...'}
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
