import { useEffect } from 'react'
import { useAuthStore } from './store/useAuthStore'
import LoginPage from './pages/LoginPage'
import MainLayout from './pages/MainLayout'

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

  return user ? <MainLayout /> : <LoginPage />
}
