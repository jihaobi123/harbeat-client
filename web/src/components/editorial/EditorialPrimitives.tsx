import { useId } from 'react'
import type { ElementType, PropsWithChildren } from 'react'

type NumberedSectionProps = PropsWithChildren<{
  number: string
  title: string
  as?: ElementType
  className?: string
  bodyClassName?: string
}>

export function NumberedSection({
  number,
  title,
  as: Root = 'section',
  className = '',
  bodyClassName = '',
  children,
}: NumberedSectionProps) {
  const headingId = useId()

  return (
    <Root className={`editorial-section ${className}`.trim()} aria-labelledby={headingId}>
      <div className="editorial-section__heading">
        <span className="editorial-section__number" aria-hidden="true">{number}</span>
        <h2 id={headingId}>{title}</h2>
      </div>
      <div className={`editorial-section__body ${bodyClassName}`.trim()}>{children}</div>
    </Root>
  )
}

export function StatusTag({
  tone,
  children,
  className = '',
}: PropsWithChildren<{
  tone: 'online' | 'info' | 'warning' | 'neutral'
  className?: string
}>) {
  return (
    <span className={`status-tag status-tag--${tone} ${className}`.trim()}>
      <span aria-hidden="true">●</span>
      {children}
    </span>
  )
}

export function EditorialKicker({
  number,
  children,
  className = '',
}: PropsWithChildren<{ number: string; className?: string }>) {
  return (
    <div className={`editorial-kicker ${className}`.trim()}>
      <b aria-hidden="true">{number}</b>
      <span>{children}</span>
    </div>
  )
}
