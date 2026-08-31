import type { ReactNode } from 'react'

export type EditorialIconName =
  | 'library'
  | 'search'
  | 'discover'
  | 'headphones'
  | 'mixer'
  | 'profile'
  | 'tag'
  | 'upload'
  | 'menu'
  | 'play'
  | 'pause'
  | 'volume'
  | 'close'
  | 'arrow'

const paths: Record<EditorialIconName, ReactNode> = {
  library: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="2" /></>,
  search: <><circle cx="10" cy="10" r="6" /><path d="m15 15 5 5" /></>,
  discover: <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z" />,
  headphones: <><path d="M4 13a8 8 0 0 1 16 0v6h-4v-6h4M4 13v6h4v-6Z" /></>,
  mixer: <><path d="M5 4v16M12 4v16M19 4v16" /><circle cx="5" cy="9" r="2" /><circle cx="12" cy="15" r="2" /><circle cx="19" cy="8" r="2" /></>,
  profile: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  tag: <><path d="M4 4h7l9 9-7 7-9-9Z" /><circle cx="8" cy="8" r="1" /></>,
  upload: <><path d="M12 16V4m-5 5 5-5 5 5" /><path d="M4 16v4h16v-4" /></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  play: <path d="m8 5 11 7-11 7Z" />,
  pause: <path d="M8 5v14M16 5v14" />,
  volume: <><path d="M4 10v4h4l5 4V6l-5 4Z" /><path d="M17 9a4 4 0 0 1 0 6" /></>,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
}

export function EditorialIcon({
  name,
  label,
  decorative = false,
  className = '',
}: {
  name: EditorialIconName
  label?: string
  decorative?: boolean
  className?: string
}) {
  return (
    <svg
      className={`editorial-icon ${className}`.trim()}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : label}
      role={decorative ? undefined : 'img'}
      focusable="false"
    >
      {paths[name]}
    </svg>
  )
}
