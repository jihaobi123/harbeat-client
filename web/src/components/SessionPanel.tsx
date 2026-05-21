import { useAuthStore } from '../store/useAuthStore'
import MixtapeBuilder from './MixtapeBuilder'
import NewMixFeatures from './NewMixFeatures'

export default function SessionPanel() {
  const { user } = useAuthStore()

  if (!user) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-center text-gray-500">
        请先登录以使用 DJ Session 功能
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-auto p-4 sm:p-6 space-y-4">
      <div className="street-sticker bg-surface-light p-4">
        <h2 className="street-title text-xl sm:text-2xl">🎧 DJ Session</h2>
        <p className="text-xs text-gray-500 mt-1">
          导入歌单 / 风格搜索 / vibe 推荐 → 选择乐段 + 打标签 → 加入待混音列表 →
          下方 8 种 Mix 策略 + 能量曲线 + Loop/切歌/Flourish/MC 语音
        </p>
      </div>

      <MixtapeBuilder />
      <NewMixFeatures />
    </div>
  )
}
