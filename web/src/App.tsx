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
      <div className="h-screen flex items-center justify-center bg-surface">
        <div className="text-gray-400 text-lg">加载中...</div>
      </div>
    )
  }

  return user ? <MainLayout /> : <LoginPage />
}
