import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { BrandIllustration } from './BrandIllustration'
import { EditorialIcon } from './EditorialIcon'
import { NumberedSection, StatusTag } from './EditorialPrimitives'
import LoginPage from '../../pages/LoginPage'

describe('editorial visual primitives', () => {
  it('renders numbered sections with a real heading relationship', () => {
    const html = renderToStaticMarkup(
      <NumberedSection number="02" title="元素出现时间" as="section">
        <p>timeline</p>
      </NumberedSection>,
    )

    expect(html).toContain('02')
    expect(html).toContain('元素出现时间')
    expect(html).toContain('aria-labelledby=')
  })

  it('does not rely on color alone for status', () => {
    const html = renderToStaticMarkup(<StatusTag tone="online">在线</StatusTag>)

    expect(html).toContain('status-tag--online')
    expect(html).toContain('在线')
    expect(html).toContain('aria-hidden="true"')
  })

  it('gives decorative illustrations and icons correct accessibility semantics', () => {
    expect(renderToStaticMarkup(<BrandIllustration variant="turntable" />)).toContain('aria-hidden="true"')
    expect(renderToStaticMarkup(<EditorialIcon name="library" label="曲库" />)).toContain('aria-label="曲库"')
  })

  it('keeps login and registration entry points inside the editorial identity', () => {
    const html = renderToStaticMarkup(<LoginPage />)

    expect(html).toContain('YOUR BEAT')
    expect(html).toContain('USERNAME')
    expect(html).toContain('REGISTER')
    expect(html).toContain('auth-page__hero')
  })
})
