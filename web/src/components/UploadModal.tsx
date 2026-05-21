import { useState, useRef } from 'react'
import { useMusicStore } from '../store/useMusicStore'

export default function UploadModal({ onClose }: { onClose: () => void }) {
  const { uploadFile, uploading } = useMusicStore()
  const [files, setFiles] = useState<File[]>([])
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const [progress, setProgress] = useState(0)
  const [total, setTotal] = useState(0)

  const handleFiles = (fileList: FileList) => {
    const arr = Array.from(fileList).filter((f) => {
      const ext = f.name.split('.').pop()?.toLowerCase() || ''
      return ['mp3', 'flac', 'wav', 'ogg', 'aac', 'm4a', 'opus'].includes(ext)
    })
    setFiles((prev) => [...prev, ...arr])
  }

  const handleUpload = async () => {
    setTotal(files.length)
    setProgress(0)
    for (const file of files) {
      const name = file.name.replace(/\.[^.]+$/, '')
      let title = name
      let artist = 'Unknown Artist'
      if (name.includes(' - ')) {
        const parts = name.split(' - ')
        artist = parts[0].trim()
        title = parts.slice(1).join(' - ').trim()
      }
      await uploadFile(file, title, artist)
      setProgress((p) => p + 1)
    }
    onClose()
  }

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx))
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-surface-light rounded-2xl w-full max-w-lg mx-2 sm:mx-4 p-4 sm:p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">上传音乐</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-xl">×</button>
        </div>

        {/* Drop zone */}
        <div
          className={`border-2 border-dashed rounded-xl p-4 sm:p-8 text-center transition cursor-pointer ${
            dragOver ? 'border-primary bg-primary/10' : 'border-gray-600 hover:border-gray-500'
          }`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
          onClick={() => inputRef.current?.click()}
        >
          <div className="text-3xl mb-2">📁</div>
          <div className="text-sm text-gray-400">拖拽文件到此处，或点击选择</div>
          <div className="text-xs text-gray-500 mt-1">支持 MP3, FLAC, WAV, OGG, AAC, M4A</div>
          <input
            ref={inputRef}
            type="file"
            accept=".mp3,.flac,.wav,.ogg,.aac,.m4a,.opus"
            multiple
            className="hidden"
            onChange={(e) => e.target.files && handleFiles(e.target.files)}
          />
        </div>

        {/* File list */}
        {files.length > 0 && (
          <div className="mt-4 max-h-40 overflow-y-auto space-y-1">
            {files.map((file, idx) => (
              <div key={idx} className="flex items-center justify-between bg-surface rounded-lg px-3 py-2">
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white truncate">{file.name}</div>
                  <div className="text-xs text-gray-500">{(file.size / (1024 * 1024)).toFixed(1)} MB</div>
                </div>
                <button
                  onClick={() => removeFile(idx)}
                  className="text-gray-500 hover:text-red-400 ml-2"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Upload progress */}
        {uploading && total > 0 && (
          <div className="mt-4">
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>上传中...</span>
              <span>{progress}/{total}</span>
            </div>
            <div className="h-1.5 bg-surface rounded-full overflow-hidden">
              <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${(progress / total) * 100}%` }} />
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3 mt-5">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-400 hover:text-white transition"
          >
            取消
          </button>
          <button
            onClick={handleUpload}
            disabled={files.length === 0 || uploading}
            className="px-6 py-2 bg-primary hover:bg-primary-dark disabled:opacity-50 text-white text-sm font-medium rounded-lg transition"
          >
            {uploading ? `上传中 (${progress}/${total})` : `上传 ${files.length} 个文件`}
          </button>
        </div>
      </div>
    </div>
  )
}
