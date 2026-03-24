export function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '0:00'
  const min = Math.floor(seconds / 60)
  const sec = Math.floor(seconds % 60)
  return `${min}:${sec.toString().padStart(2, '0')}`
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function getAudioDuration(url: string): Promise<number> {
  return new Promise((resolve) => {
    const audio = new Audio()
    audio.addEventListener('loadedmetadata', () => {
      resolve(audio.duration)
    })
    audio.addEventListener('error', () => {
      resolve(0)
    })
    audio.preload = 'metadata'
    audio.src = url
  })
}
