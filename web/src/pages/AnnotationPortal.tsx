import { useCallback, useState } from 'react'

import AnnotationWorkbench from './AnnotationWorkbench'
import { useAuthStore } from '../store/useAuthStore'


export default function AnnotationPortal() {
  const { user, doLogout } = useAuthStore()
  const [dirty, setDirty] = useState(false)

  const confirmLeave = useCallback(() => (
    !dirty || window.confirm('这首歌还有未保存的标注。确定离开吗？')
  ), [dirty])

  const leavePortal = () => {
    if (confirmLeave()) window.location.assign('/')
  }

  const logout = () => {
    if (!confirmLeave()) return
    doLogout()
  }

  return (
    <div className="h-screen flex flex-col bg-surface street-theme p-1 sm:p-2 gap-1 sm:gap-2">
      <header className="street-sticker bg-surface-light px-3 sm:px-5 py-3 flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div>
          <div className="text-2xl street-title leading-none">HarBeat 标注工作台</div>
          <div className="text-xs street-subtitle mt-1">公共 Pilot · 每位标注者独立保存</div>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="px-3 py-2 bg-surface-lighter border-2 border-black rounded-md">
            标注者：{user?.username}
          </span>
          <button className="px-3 py-2 bg-white" onClick={leavePortal}>返回原网站</button>
          <button className="px-3 py-2 bg-white" onClick={logout}>退出登录</button>
        </div>
      </header>
      <AnnotationWorkbench onDirtyChange={setDirty} />
    </div>
  )
}
