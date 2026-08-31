# HarBeat Web Editorial Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Jetson 公网网页端的登录注册、原网站和 `/annotate` 统一改成已确认的 A「编辑台」视觉，同时保持功能、数据、接口和路由不变。

**Architecture:** 保留现有 React 页面、Zustand Store 和 API Client，在它们外面增加一层无业务状态的视觉组件。全站样式由一套本地字体、设计变量、编号模块、线描图标和原创 SVG 插画驱动；现有大组件只调整结构类名和可访问属性，不复制业务逻辑。

**Tech Stack:** React 18、TypeScript、Vite、Tailwind CSS、Vitest、React DOM server renderer、内联 SVG、Fontsource 本地字体包

---

## 文件结构

新增文件：

- `web/src/components/editorial/EditorialPrimitives.tsx`：编号标题条、状态标签和统一图标按钮。
- `web/src/components/editorial/EditorialIcon.tsx`：替代页面表情符号的线描 SVG 图标。
- `web/src/components/editorial/BrandIllustration.tsx`：唱片、耳机、音箱三种原创装饰插画。
- `web/src/components/editorial/EditorialPrimitives.test.tsx`：视觉组件的静态结构和可访问性测试。

主要修改文件：

- `web/package.json`、`web/package-lock.json`、`web/src/main.tsx`：本地打包 Oswald 展示字体。
- `web/src/index.css`：设计变量、页面框架、组件状态、响应式和减少动态效果规则。
- `web/src/App.tsx`、`web/src/pages/LoginPage.tsx`：加载、登录和注册入口。
- `web/src/pages/MainLayout.tsx`、`web/src/components/Sidebar.tsx`、`web/src/components/AudioPlayer.tsx`：桌面框架、移动导航和常驻播放器。
- `web/src/components/SongList.tsx`、`SongDetail.tsx`、`PlatformSearch.tsx`、`RecommendPanel.tsx`、`VibeSearch.tsx`、`SessionPanel.tsx`、`DjControlPanel.tsx`、`ProfilePanel.tsx`、`SeamlessPlayer.tsx`、`WaveformPlayer.tsx`：原网站功能区的统一视觉。
- `web/src/components/UploadModal.tsx`、`PlaylistImportModal.tsx`：桌面弹窗和移动端面板。
- `web/src/pages/AnnotationPortal.tsx`、`AnnotationWorkbench.tsx`、`web/src/components/PresenceAnnotationPanel.tsx`、`PresenceTimeline.tsx`：公共标注工作台。

不修改 `web/src/api`、`web/src/store` 和任何后端文件。

### Task 1: 用测试锁定视觉组件契约

**Files:**
- Create: `web/src/components/editorial/EditorialPrimitives.test.tsx`

- [ ] **Step 1: 写失败测试**

```tsx
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { BrandIllustration } from './BrandIllustration'
import { EditorialIcon } from './EditorialIcon'
import { NumberedSection, StatusTag } from './EditorialPrimitives'

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
})
```

- [ ] **Step 2: 运行测试，确认因组件尚不存在而失败**

Run: `cd web && npm test -- EditorialPrimitives.test.tsx`  
Expected: FAIL，提示无法导入 `EditorialPrimitives`、`EditorialIcon` 或 `BrandIllustration`。

- [ ] **Step 3: 提交测试**

```bash
git add web/src/components/editorial/EditorialPrimitives.test.tsx
git commit -m "test: define editorial visual primitives"
```

### Task 2: 建立本地字体和纯视觉组件

**Files:**
- Create: `web/src/components/editorial/EditorialPrimitives.tsx`
- Create: `web/src/components/editorial/EditorialIcon.tsx`
- Create: `web/src/components/editorial/BrandIllustration.tsx`
- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Modify: `web/src/main.tsx`

- [ ] **Step 1: 安装构建时打包的展示字体**

Run: `cd web && npm install @fontsource/oswald`  
Expected: `package.json` 和 `package-lock.json` 增加 `@fontsource/oswald`，安装过程无 audit error。

- [ ] **Step 2: 在入口加载需要的本地字重**

把 `web/src/main.tsx` 的样式导入区改成：

```tsx
import '@fontsource/oswald/500.css'
import '@fontsource/oswald/600.css'
import '@fontsource/oswald/700.css'
import './index.css'
```

- [ ] **Step 3: 实现编号模块和状态标签**

```tsx
import type { ElementType, PropsWithChildren } from 'react'

type NumberedSectionProps = PropsWithChildren<{
  number: string
  title: string
  as?: ElementType
  className?: string
}>

export function NumberedSection({ number, title, as: Root = 'section', className = '', children }: NumberedSectionProps) {
  const headingId = `editorial-${number}-${title.replace(/\s+/g, '-').toLowerCase()}`
  return (
    <Root className={`editorial-section ${className}`.trim()} aria-labelledby={headingId}>
      <div className="editorial-section__heading">
        <span className="editorial-section__number" aria-hidden="true">{number}</span>
        <h2 id={headingId}>{title}</h2>
      </div>
      <div className="editorial-section__body">{children}</div>
    </Root>
  )
}

export function StatusTag({ tone, children }: PropsWithChildren<{ tone: 'online' | 'info' | 'warning' | 'neutral' }>) {
  return <span className={`status-tag status-tag--${tone}`}><span aria-hidden="true">●</span>{children}</span>
}
```

- [ ] **Step 4: 实现统一线描图标**

`EditorialIcon` 支持 `library`、`search`、`discover`、`headphones`、`mixer`、`profile`、`tag`、`upload`、`menu`、`play`、`pause`、`volume`、`close`。每个分支返回同一个 `24 × 24` SVG 外壳，装饰用法传 `decorative`，交互用法传 `label`：

```tsx
export type EditorialIconName = 'library' | 'search' | 'discover' | 'headphones' | 'mixer' | 'profile' | 'tag' | 'upload' | 'menu' | 'play' | 'pause' | 'volume' | 'close'

export function EditorialIcon({ name, label, decorative = false, className = '' }: {
  name: EditorialIconName
  label?: string
  decorative?: boolean
  className?: string
}) {
  const paths: Record<EditorialIconName, React.ReactNode> = {
    library: <><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2"/></>,
    search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></>,
    discover: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/></>,
    headphones: <><path d="M4 13a8 8 0 0 1 16 0v6h-4v-6h4M4 13v6h4v-6Z"/></>,
    mixer: <><path d="M5 4v16M12 4v16M19 4v16"/><circle cx="5" cy="9" r="2"/><circle cx="12" cy="15" r="2"/><circle cx="19" cy="8" r="2"/></>,
    profile: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
    tag: <><path d="M4 4h7l9 9-7 7-9-9Z"/><circle cx="8" cy="8" r="1"/></>,
    upload: <><path d="M12 16V4m-5 5 5-5 5 5"/><path d="M4 16v4h16v-4"/></>,
    menu: <path d="M4 7h16M4 12h16M4 17h16"/>,
    play: <path d="m8 5 11 7-11 7Z"/>, pause: <path d="M8 5v14M16 5v14"/>,
    volume: <><path d="M4 10v4h4l5 4V6l-5 4Z"/><path d="M17 9a4 4 0 0 1 0 6"/></>,
    close: <path d="m6 6 12 12M18 6 6 18"/>,
  }
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden={decorative || undefined} aria-label={decorative ? undefined : label} role={decorative ? undefined : 'img'}>{paths[name]}</svg>
}
```

- [ ] **Step 5: 实现原创装饰插画**

`BrandIllustration` 提供 `turntable`、`headphones`、`speakers` 三个内联 SVG。共同外壳如下，图形只使用 `currentColor`、`var(--editorial-blue)`、`var(--editorial-yellow)` 和 `var(--editorial-red)`：

```tsx
export function BrandIllustration({ variant, className = '' }: { variant: 'turntable' | 'headphones' | 'speakers'; className?: string }) {
  return (
    <svg className={`brand-illustration ${className}`.trim()} viewBox="0 0 220 150" aria-hidden="true" focusable="false">
      {variant === 'turntable' && <><path d="M20 35h180v95H20z"/><circle cx="92" cy="82" r="38"/><circle cx="92" cy="82" r="10"/><path d="m158 52 22 50m-33 3 35-16"/></>}
      {variant === 'headphones' && <><path d="M53 92a57 57 0 0 1 114 0"/><path d="M42 86h28v50H42zM150 86h28v50h-28z"/><path d="M58 36 45 22m111 14 13-14"/></>}
      {variant === 'speakers' && <><path d="M35 28h66v108H35zM119 16h66v120h-66z"/><circle cx="68" cy="62" r="14"/><circle cx="68" cy="105" r="23"/><circle cx="152" cy="53" r="15"/><circle cx="152" cy="101" r="25"/></>}
    </svg>
  )
}
```

- [ ] **Step 6: 运行组件测试**

Run: `cd web && npm test -- EditorialPrimitives.test.tsx`  
Expected: 3 tests PASS。

- [ ] **Step 7: 提交视觉底层**

```bash
git add web/package.json web/package-lock.json web/src/main.tsx web/src/components/editorial
git commit -m "feat: add editorial visual primitives"
```

### Task 3: 重建全站设计变量和基础状态

**Files:**
- Modify: `web/src/index.css`

- [ ] **Step 1: 替换外部字体导入并建立设计变量**

删除 `@import url('https://fonts.googleapis.com/css2?family=Bangers&family=Permanent+Marker&display=swap')`，在 `:root` 定义：

```css
:root {
  --editorial-paper: #f4efe4;
  --editorial-paper-bright: #fffdf7;
  --editorial-ink: #0b0b0b;
  --editorial-acid: #c9f400;
  --editorial-blue: #075bc8;
  --editorial-red: #f13a20;
  --editorial-yellow: #f3c52e;
  --editorial-green: #008f68;
  --editorial-shadow: 5px 5px 0 var(--editorial-ink);
  --editorial-font-display: 'Oswald', 'Arial Narrow', sans-serif;
  --editorial-font-body: 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif;
}
```

- [ ] **Step 2: 实现统一卡片、按钮、字段和焦点状态**

```css
.street-theme { background: var(--editorial-paper); color: var(--editorial-ink); }
.street-sticker, .editorial-section { border: 3px solid var(--editorial-ink); border-radius: 2px; box-shadow: var(--editorial-shadow); background: var(--editorial-paper-bright); }
.street-theme button { min-height: 44px; border: 2px solid var(--editorial-ink); border-radius: 2px; box-shadow: 3px 3px 0 var(--editorial-ink); font-weight: 700; }
.street-theme button:focus-visible, .street-theme input:focus-visible, .street-theme select:focus-visible, .street-theme textarea:focus-visible { outline: 4px solid var(--editorial-blue); outline-offset: 3px; }
.street-theme button:disabled { opacity: .48; cursor: not-allowed; transform: none; box-shadow: 2px 2px 0 var(--editorial-ink); }
.street-theme input, .street-theme select, .street-theme textarea { min-height: 44px; border: 2px solid var(--editorial-ink) !important; border-radius: 2px !important; box-shadow: 2px 2px 0 var(--editorial-ink); }
```

- [ ] **Step 3: 实现编号模块、状态标签和插画样式**

```css
.editorial-section__heading { min-height: 42px; display:flex; align-items:stretch; border-bottom:3px solid var(--editorial-ink); }
.editorial-section__number { min-width:46px; display:grid; place-items:center; color:#fff; background:var(--editorial-ink); font:700 1.25rem/1 var(--editorial-font-display); }
.editorial-section__heading h2 { margin:0; padding:.55rem .75rem; font:700 1.1rem/1.1 var(--editorial-font-display); text-transform:uppercase; }
.editorial-section__body { padding:1rem; }
.status-tag { display:inline-flex; gap:.4rem; align-items:center; border:2px solid var(--editorial-ink); padding:.35rem .55rem; font-size:.75rem; font-weight:800; }
.status-tag--online { background:var(--editorial-acid); }
.status-tag--warning { background:var(--editorial-red); }
.brand-illustration { width:100%; height:auto; fill:var(--editorial-yellow); stroke:var(--editorial-ink); stroke-width:4; stroke-linecap:round; stroke-linejoin:round; }
```

- [ ] **Step 4: 增加响应式和减少动态效果规则**

```css
@media (max-width: 767px) {
  .editorial-desktop-only { display:none !important; }
  .editorial-mobile-stack { display:flex !important; flex-direction:column !important; }
  .street-sticker, .editorial-section { box-shadow:3px 3px 0 var(--editorial-ink); }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior:auto !important; transition-duration:.01ms !important; animation-duration:.01ms !important; animation-iteration-count:1 !important; }
  .street-theme button:hover, .street-theme button:active { transform:none; }
}
```

- [ ] **Step 5: 检查 CSS 和生产构建**

Run: `cd web && npm run build`  
Expected: TypeScript 与 Vite build PASS；构建日志不再请求 Google Fonts。

- [ ] **Step 6: 提交全站视觉变量**

```bash
git add web/src/index.css
git commit -m "feat: establish editorial web theme"
```

### Task 4: 改造登录入口和应用加载状态

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/pages/LoginPage.tsx`

- [ ] **Step 1: 为登录与注册结构补充静态测试**

在 `EditorialPrimitives.test.tsx` 增加：

```tsx
import LoginPage from '../../pages/LoginPage'

it('keeps login and register entry points visible', () => {
  const html = renderToStaticMarkup(<LoginPage />)
  expect(html).toContain('YOUR BEAT')
  expect(html).toContain('USERNAME')
  expect(html).toContain('REGISTER')
})
```

- [ ] **Step 2: 运行测试并确认主视觉尚不存在**

Run: `cd web && npm test -- EditorialPrimitives.test.tsx`  
Expected: FAIL，`YOUR BEAT` 未出现。

- [ ] **Step 3: 改造登录页面结构**

保留 `handleSubmit`、错误区和全部表单字段状态。在当前 `<form>` 前加入品牌主视觉：

```tsx
<section className="auth-page__hero" aria-labelledby="auth-brand-title">
  <div className="editorial-kicker"><b>01</b><span>HARBEAT / PERSONAL</span></div>
  <h1 id="auth-brand-title">YOUR BEAT.<br />YOUR MARK.</h1>
  <p>hiphop street music platform</p>
  <BrandIllustration variant="turntable" />
</section>
```

现有表单的类名改为 `auth-page__form street-sticker`，表单第一个子节点加入：

```tsx
<div className="editorial-kicker"><b>02</b><span>{isRegister ? 'REGISTER / 注册' : 'LOGIN / 登录'}</span></div>
```

品牌主视觉和表单共同放入 `<main className="auth-page street-theme">`，当前字段 JSX 不改顺序。

- [ ] **Step 4: 把加载状态改成同一视觉语言**

```tsx
<div className="app-loading street-theme" role="status" aria-live="polite">
  <div className="editorial-kicker"><b>00</b><span>HARBEAT</span></div>
  <p>LOADING YOUR WORKSPACE…</p>
</div>
```

- [ ] **Step 5: 运行测试与构建**

Run: `cd web && npm test -- EditorialPrimitives.test.tsx && npm run build`  
Expected: tests PASS，build PASS。

- [ ] **Step 6: 提交入口页面**

```bash
git add web/src/App.tsx web/src/pages/LoginPage.tsx web/src/components/editorial/EditorialPrimitives.test.tsx
git commit -m "feat: redesign authentication entry"
```

### Task 5: 改造主站框架、导航和播放器

**Files:**
- Modify: `web/src/pages/MainLayout.tsx`
- Modify: `web/src/components/Sidebar.tsx`
- Modify: `web/src/components/AudioPlayer.tsx`

- [ ] **Step 1: 在 `MainLayout` 加入编号品牌条和移动导航**

桌面头部使用 `editorial-topbar`；移动底部导航把现有视图映射为音乐、发现、DJ、标注、我的。映射不创建新业务状态：

```tsx
const MOBILE_NAV = [
  { id: 'library' as const, label: '音乐', icon: 'library' as const },
  { id: 'recommend' as const, label: '发现', icon: 'discover' as const },
  { id: 'dj' as const, label: 'DJ', icon: 'mixer' as const },
  { id: 'annotation' as const, label: '标注', icon: 'tag' as const },
  { id: 'profile' as const, label: '我的', icon: 'profile' as const },
]
```

标注项继续执行 `window.location.assign('/annotate')`；其他项调用 `handleViewChange`。`PlatformSearch` 和 `SessionPanel` 继续从侧栏和对应分组进入。

- [ ] **Step 2: 用线描图标替换侧栏表情符号**

把 `NAV_ITEMS` 改为：

```tsx
const NAV_ITEMS = [
  { id: 'library', icon: 'library', label: 'Library' },
  { id: 'platform', icon: 'search', label: 'Search' },
  { id: 'recommend', icon: 'discover', label: 'Discover' },
  { id: 'session', icon: 'headphones', label: 'DJ Session' },
  { id: 'dj', icon: 'mixer', label: 'DJ Control' },
  { id: 'profile', icon: 'profile', label: 'Profile' },
] satisfies { id: NavView; icon: EditorialIconName; label: string }[]
```

按钮内容改为 `<EditorialIcon name={item.icon} decorative /><span>{item.label}</span>`，公共标注入口使用 `tag`。

- [ ] **Step 3: 把播放器改成黑底控制条并补足可访问名称**

播放器根节点使用 `editorial-player`，播放键增加完整可访问名称：

```tsx
<button onClick={togglePlay} className="editorial-player__play" aria-label={isPlaying ? '暂停' : '播放'}>
  <EditorialIcon name={isPlaying ? 'pause' : 'play'} decorative />
</button>
```

在当前两个 `type="range"` 输入中分别加入：

```tsx
aria-label="播放进度"
aria-label="音量"
```

- [ ] **Step 4: 为 1024、768、390 像素写框架样式**

```css
.editorial-app { min-height:100dvh; display:grid; grid-template-rows:auto minmax(0,1fr) auto; gap:.6rem; padding:.6rem; }
.editorial-workspace { display:grid; grid-template-columns:240px minmax(0,1fr); gap:.6rem; min-height:0; }
.editorial-mobile-nav { display:none; }
.editorial-player { min-height:72px; color:#fff; background:#0b0b0b !important; border:3px solid #0b0b0b; }
@media (max-width: 1023px) { .editorial-workspace { grid-template-columns:200px minmax(0,1fr); } }
@media (max-width: 767px) { .editorial-workspace { display:block; padding-bottom:64px; } .editorial-mobile-nav { position:fixed; left:.5rem; right:.5rem; bottom:.5rem; z-index:35; display:grid; grid-template-columns:repeat(5,1fr); } }
```

- [ ] **Step 5: 运行现有路由测试和构建**

Run: `cd web && npm test -- routing.test.ts && npm run build`  
Expected: route tests PASS，build PASS。

- [ ] **Step 6: 提交主框架**

```bash
git add web/src/pages/MainLayout.tsx web/src/components/Sidebar.tsx web/src/components/AudioPlayer.tsx web/src/index.css
git commit -m "feat: redesign web shell and navigation"
```

### Task 6: 统一原网站功能页面

**Files:**
- Modify: `web/src/components/SongList.tsx`
- Modify: `web/src/components/SongDetail.tsx`
- Modify: `web/src/components/PlatformSearch.tsx`
- Modify: `web/src/components/RecommendPanel.tsx`
- Modify: `web/src/components/VibeSearch.tsx`
- Modify: `web/src/components/SessionPanel.tsx`
- Modify: `web/src/components/DjControlPanel.tsx`
- Modify: `web/src/components/ProfilePanel.tsx`
- Modify: `web/src/components/SeamlessPlayer.tsx`
- Modify: `web/src/components/WaveformPlayer.tsx`

- [ ] **Step 1: 为每个顶级功能区添加稳定的页面类和编号标题条**

编号固定为：曲库 `01`、搜索 `02`、推荐 `03`、DJ Session `04`、DJ Control `05`、Profile `06`。每个根节点使用 `feature-panel feature-panel--<name>`。例如 `RecommendPanel` 的标题区替换为：

```tsx
<div className="feature-panel__heading">
  <span aria-hidden="true">03</span>
  <div><h1>DISCOVER / 发现音乐</h1><p>自动推荐不同舞种、场景下适合的音乐</p></div>
</div>
```

`SongList` 和 `SongDetail` 保持并排业务关系，只给列表表头、歌曲行、详情卡和操作菜单增加 `song-list__*`、`song-detail__*` 类。

- [ ] **Step 2: 统一卡片、标签、空状态和错误状态**

把页面现有语义颜色映射到以下类，不删除文字。`RecommendPanel` 的错误与空状态改成：

```tsx
<div className="editorial-state editorial-state--error" role="alert">{error}</div>
<div className="editorial-state editorial-state--empty">
  <BrandIllustration variant="headphones" />
  <p>服务器上还没有歌曲</p>
  <p>去「在线搜索」下载一些歌曲吧</p>
</div>
```

动态标签保持当前 `{section.title}`、`{section.songs.length}` 和 `{section.description}` 数据，只把外框类名改为 `editorial-chip`；当前选中状态追加 `editorial-chip--active`。

- [ ] **Step 3: 统一播放器和波形模块**

`SeamlessPlayer` 根节点使用 `deck-card`，状态头使用 `deck-card__status`；`WaveformPlayer` 使用 `waveform-card`。播放、暂停和跳转按钮全部补 `aria-label`，原有事件处理保持不变。

- [ ] **Step 4: 添加功能页面样式**

```css
.feature-panel { flex:1; min-width:0; min-height:0; overflow:auto; border:3px solid var(--editorial-ink); background:var(--editorial-paper-bright); }
.feature-panel__heading { display:flex; border-bottom:3px solid var(--editorial-ink); background:var(--editorial-paper); }
.feature-panel__heading > span { min-width:52px; display:grid; place-items:center; background:var(--editorial-ink); color:#fff; font:700 1.35rem var(--editorial-font-display); }
.feature-panel__heading h1 { margin:0; font:700 1.6rem/1 var(--editorial-font-display); }
.editorial-state { border:3px solid var(--editorial-ink); padding:1rem; background:#fff; }
.editorial-state--error { background:#ffd8cf; }
.editorial-chip { border:2px solid var(--editorial-ink); border-radius:0; padding:.3rem .5rem; }
.editorial-chip--active { background:var(--editorial-acid); }
```

- [ ] **Step 5: 运行全部前端测试和构建**

Run: `cd web && npm test && npm run build`  
Expected: 全部现有测试与新增测试 PASS，build PASS。

- [ ] **Step 6: 提交功能页面**

```bash
git add web/src/components/SongList.tsx web/src/components/SongDetail.tsx web/src/components/PlatformSearch.tsx web/src/components/RecommendPanel.tsx web/src/components/VibeSearch.tsx web/src/components/SessionPanel.tsx web/src/components/DjControlPanel.tsx web/src/components/ProfilePanel.tsx web/src/components/SeamlessPlayer.tsx web/src/components/WaveformPlayer.tsx web/src/index.css
git commit -m "feat: restyle web feature panels"
```

### Task 7: 改造上传与歌单导入弹窗

**Files:**
- Modify: `web/src/components/UploadModal.tsx`
- Modify: `web/src/components/PlaylistImportModal.tsx`

- [ ] **Step 1: 统一弹窗结构和关闭按钮**

两个弹窗共用 `editorial-modal-backdrop`、`editorial-modal`、`editorial-modal__heading` 和 `editorial-modal__body`。上传弹窗标题改成：

```tsx
<div className="editorial-modal-backdrop" role="presentation">
  <section className="editorial-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
    <header className="editorial-modal__heading">
      <span aria-hidden="true">07</span>
      <h2 id="modal-title">上传音乐</h2>
      <button onClick={onClose} aria-label="关闭"><EditorialIcon name="close" decorative /></button>
    </header>
  </section>
</div>
```

现有上传内容移入紧跟标题后的 `<div className="editorial-modal__body">`。导入歌单使用编号 `08`，标题继续由当前 `stage` 表达式生成：

```tsx
<h2 id="playlist-import-title">
  {stage === 'parse' && '导入歌单'}
  {stage === 'select' && '选择歌曲'}
  {stage === 'search' && '搜索音源中...'}
  {stage === 'tag' && '设置标签并下载'}
  {stage === 'downloading' && '下载中...'}
  {stage === 'done' && '导入完成'}
</h2>
```

字段、进度、平台选择和提交事件不变。

- [ ] **Step 2: 添加桌面弹窗和移动底部面板样式**

```css
.editorial-modal-backdrop { position:fixed; inset:0; z-index:50; display:grid; place-items:center; padding:1rem; background:rgba(11,11,11,.72); }
.editorial-modal { width:min(800px,100%); max-height:92dvh; overflow:auto; border:4px solid var(--editorial-ink); background:var(--editorial-paper); box-shadow:8px 8px 0 var(--editorial-ink); }
.editorial-modal__heading { position:sticky; top:0; z-index:2; display:flex; align-items:stretch; border-bottom:3px solid var(--editorial-ink); background:#fff; }
@media (max-width:767px) { .editorial-modal-backdrop { align-items:end; padding:0; } .editorial-modal { width:100%; max-height:94dvh; box-shadow:none; border-width:4px 0 0; } }
```

- [ ] **Step 3: 运行构建**

Run: `cd web && npm run build`  
Expected: PASS。

- [ ] **Step 4: 提交弹窗改版**

```bash
git add web/src/components/UploadModal.tsx web/src/components/PlaylistImportModal.tsx web/src/index.css
git commit -m "feat: redesign web modal flows"
```

### Task 8: 改造公共标注工作台

**Files:**
- Modify: `web/src/pages/AnnotationPortal.tsx`
- Modify: `web/src/pages/AnnotationWorkbench.tsx`
- Modify: `web/src/components/PresenceAnnotationPanel.tsx`
- Modify: `web/src/components/PresenceTimeline.tsx`
- Modify: `web/src/index.css`

- [ ] **Step 1: 把 Portal 头部改成在线状态编辑台**

```tsx
<header className="annotation-header street-sticker">
  <div className="annotation-header__title"><span aria-hidden="true">03</span><div><h1>HARBEAT / 标注工作台</h1><p>公共 Pilot · 每位标注者独立保存</p></div></div>
  <div className="annotation-header__actions">
    <StatusTag tone="online">{user?.username} · ONLINE</StatusTag>
    <button onClick={leavePortal}>返回原网站</button>
    <button onClick={logout}>退出登录</button>
  </div>
</header>
```

`confirmLeave`、`leavePortal` 和 `logout` 原样保留。

- [ ] **Step 2: 为 Workbench 增加稳定区域类**

根节点使用 `annotation-workbench`。歌曲选择区、运输控制、Bar 选择、段落、元素状态和保存条依次增加：

```text
annotation-track-picker
annotation-transport
annotation-bars
annotation-sections
annotation-elements
annotation-savebar
```

现有 `onClick`、`onChange`、`playSelection`、`setLoopSelection`、`applySectionLabel`、`applyElementState` 和 `save` 调用不变。空状态中的 `🏷️` 替换为 `<BrandIllustration variant="headphones" />`。

- [ ] **Step 3: 加强时间轴识别和移动端操作**

```css
.annotation-workbench { flex:1; min-width:0; min-height:0; overflow:auto; border:3px solid var(--editorial-ink); background:var(--editorial-paper); }
.annotation-transport { position:sticky; top:0; z-index:15; background:var(--editorial-paper-bright); }
.annotation-savebar { position:sticky; bottom:.5rem; z-index:15; border:3px solid var(--editorial-ink); background:var(--editorial-paper-bright); }
.presence-lane-body { min-width:720px; height:44px; border:2px solid var(--editorial-ink); background:repeating-linear-gradient(90deg,#eee 0 23px,#c8c8c8 23px 24px); }
.presence-playhead { width:3px; background:var(--editorial-red); }
@media (max-width:767px) { .annotation-header__actions { width:100%; overflow-x:auto; } .annotation-workbench { padding:.65rem; } .annotation-savebar { bottom:4.6rem; } }
```

- [ ] **Step 4: 保留并验证标注可访问状态**

`PresenceAnnotationPanel` 的播放器保留 `aria-label="标注试听播放器"`；加载状态保留 `role="status"`，错误保留 `role="alert"`。时间轴的元素按钮和区间拖拽按钮补充包含元素名、起止 Bar 和状态的 `aria-label`。

- [ ] **Step 5: 运行标注组件测试、路由测试和构建**

Run: `cd web && npm test -- PresenceAnnotationPanel.test.tsx PresenceTimeline.test.tsx routing.test.ts && npm run build`  
Expected: 所有指定测试 PASS，build PASS。

- [ ] **Step 6: 提交标注工作台**

```bash
git add web/src/pages/AnnotationPortal.tsx web/src/pages/AnnotationWorkbench.tsx web/src/components/PresenceAnnotationPanel.tsx web/src/components/PresenceTimeline.tsx web/src/index.css
git commit -m "feat: redesign public annotation workbench"
```

### Task 9: 全量回归与多尺寸浏览器验收

**Files:**
- Modify when defects are found: files from Tasks 2–8 only

- [ ] **Step 1: 运行完整前端检查**

Run: `cd web && npm test && npm run build`  
Expected: 所有 Vitest 测试 PASS，TypeScript 和 Vite build PASS。

- [ ] **Step 2: 检查外部运行时资源**

Run: `rg -n "fonts.googleapis.com|fonts.gstatic.com|http://|https://" web/src web/dist`  
Expected: 不出现字体或插画外链；API 客户端中已有服务地址不属于本检查失败。

- [ ] **Step 3: 在 1440 和 1024 像素检查桌面流程**

依次检查登录、注册、Library、Search、Discover、DJ Session、DJ Control、Profile、上传、歌单导入、底部播放器和 `/annotate`。每个入口可达，卡片不溢出，焦点可见，控制器可点击。

- [ ] **Step 4: 在 768 和 390 像素检查移动流程**

确认底部导航可到音乐、发现、DJ、标注和我的；搜索与 DJ Session 可从对应分组进入；迷你播放器不遮住导航；标注歌曲选择、横向时间轴和固定保存条可以操作。

- [ ] **Step 5: 检查异常与边界状态**

使用浏览器和现有测试数据检查：错误登录、长用户名、长歌名、空歌单、加载、接口失败、无音频、未保存离开确认、保存冲突和登录过期。错误文字不能被颜色或插画替代。

- [ ] **Step 6: 修复发现的问题并重复完整检查**

Run: `cd web && npm test && npm run build`  
Expected: 所有检查再次 PASS。

- [ ] **Step 7: 提交回归修复**

```bash
git add web/src web/package.json web/package-lock.json
git commit -m "fix: polish editorial responsive states"
```

如果没有产生修复，不创建空提交。

### Task 10: 发布到 Jetson 并验证数据不受影响

**Files:**
- Modify: deployment record only if the repository already uses one for releases

- [ ] **Step 1: 记录发布前版本和标注目录状态**

读取当前 release 指向、服务状态、`/` 与 `/annotate` HTTP 状态，以及持久化标注目录文件数。只记录，不改动数据。

- [ ] **Step 2: 创建新的只读 release 目录并部署构建产物**

使用现有 Jetson 发布流程，把本次提交部署到新 release 目录。API 环境变量、Nginx 规则和标注目录挂载沿用当前生产配置。

- [ ] **Step 3: 在临时端口完成上线前验收**

检查登录、本地字体、SVG 插画、主站路由、`/annotate`、音频和 API 请求。浏览器控制台无资源 404 和 JavaScript error。

- [ ] **Step 4: 切换公网版本并做双入口冒烟测试**

检查公网 `/` 和 `/annotate`；使用现有验收账号登录，读取一首 Pilot 歌曲与自己的 Revision。不要修改正式标注内容。

- [ ] **Step 5: 对比发布前后的持久化数据**

确认标注目录文件数和现有 Revision 未因前端发布变化，已有账号仍可登录，不同标注者的数据隔离规则不变。

- [ ] **Step 6: 记录发布结果**

记录 commit、release 目录、验证时间、测试结果和回滚目标。若任何关键流程失败，恢复上一个 release；持久化标注目录不回滚、不删除。
