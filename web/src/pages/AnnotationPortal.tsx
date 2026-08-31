import { useCallback, useState } from 'react'

import AnnotationWorkbench from './AnnotationWorkbench'
import { useAuthStore } from '../store/useAuthStore'
import { StatusTag } from '../components/editorial/EditorialPrimitives'


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
    <div className="annotation-portal street-theme">
      <header className="annotation-header street-sticker">
        <div className="annotation-header__title">
          <span aria-hidden="true">03</span>
          <div>
            <h1>HarBeat / 标注工作台</h1>
            <p>公共 Pilot · 每位标注者独立保存</p>
          </div>
        </div>
        <div className="annotation-header__actions text-sm">
          <StatusTag tone="online">{user?.username || '标注者'} · ONLINE</StatusTag>
          <button className="px-3 py-2 bg-white" onClick={leavePortal}>返回原网站</button>
          <button className="px-3 py-2 bg-white" onClick={logout}>退出登录</button>
        </div>
      </header>
      <AnnotationWorkbench onDirtyChange={setDirty} />
    </div>
  )
}
