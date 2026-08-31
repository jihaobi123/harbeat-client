import { useEffect } from 'react'
import { useAuthStore } from './store/useAuthStore'
import LoginPage from './pages/LoginPage'
import MainLayout from './pages/MainLayout'
import AnnotationPortal from './pages/AnnotationPortal'
import { isAnnotationRoute } from './routing'

export default function App() {
  const { user, loading, checkAuth } = useAuthStore()

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  if (loading) {
    return (
      <div className="app-loading street-theme" role="status" aria-live="polite">
        <div className="editorial-kicker"><b aria-hidden="true">00</b><span>HarBeat</span></div>
        <p>Loading your workspace…</p>
      </div>
    )
  }

  if (!user) return <LoginPage />
  return isAnnotationRoute(window.location.pathname) ? <AnnotationPortal /> : <MainLayout />
}
