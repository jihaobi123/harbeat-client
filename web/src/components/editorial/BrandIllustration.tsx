export type BrandIllustrationVariant = 'turntable' | 'headphones' | 'speakers'

export function BrandIllustration({
  variant,
  className = '',
}: {
  variant: BrandIllustrationVariant
  className?: string
}) {
  return (
    <svg
      className={`brand-illustration brand-illustration--${variant} ${className}`.trim()}
      viewBox="0 0 220 150"
      aria-hidden="true"
      focusable="false"
    >
      {variant === 'turntable' && (
        <>
          <path className="illustration-paper" d="M20 35h180v95H20z" />
          <circle className="illustration-ink" cx="92" cy="82" r="38" />
          <circle className="illustration-accent" cx="92" cy="82" r="10" />
          <path d="m158 52 22 50m-33 3 35-16" />
          <circle cx="178" cy="49" r="5" />
        </>
      )}
      {variant === 'headphones' && (
        <>
          <path className="illustration-paper" d="M53 92a57 57 0 0 1 114 0" />
          <path className="illustration-red" d="M42 86h28v50H42z" />
          <path className="illustration-blue" d="M150 86h28v50h-28z" />
          <path d="M58 36 45 22m111 14 13-14M32 63 18 56m184 7-14-7" />
        </>
      )}
      {variant === 'speakers' && (
        <>
          <path className="illustration-blue" d="M35 28h66v108H35z" />
          <path className="illustration-red" d="M119 16h66v120h-66z" />
          <circle className="illustration-paper" cx="68" cy="62" r="14" />
          <circle className="illustration-ink" cx="68" cy="105" r="23" />
          <circle className="illustration-paper" cx="152" cy="53" r="15" />
          <circle className="illustration-ink" cx="152" cy="101" r="25" />
          <path d="m104 28 9-16m79 29 15-9M24 17 12 5" />
        </>
      )}
    </svg>
  )
}
