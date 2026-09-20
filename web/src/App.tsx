import { useEffect } from 'react'
import { useAuthStore } from './store/useAuthStore'
import LoginPage from './pages/LoginPage'
import MainLayout from './pages/MainLayout'
import AnnotationPortal from './pages/AnnotationPortal'
import { isAnnotationRoute } from './routing'
import AnalysisLab from './analysis/AnalysisLab'

export default function App() {
  if (window.location.pathname === '/analysis-lab' || window.location.pathname === '/analysis-lab/') return <AnalysisLab />
  return <AuthenticatedApp />
}

function AuthenticatedApp() {
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
