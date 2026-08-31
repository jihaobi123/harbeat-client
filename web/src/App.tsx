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
      <div className="h-screen flex items-center justify-center bg-surface street-theme">
        <div className="street-sticker px-6 py-4 text-lg street-subtitle">Loading...</div>
      </div>
    )
  }

  if (!user) return <LoginPage />
  return isAnnotationRoute(window.location.pathname) ? <AnnotationPortal /> : <MainLayout />
}
