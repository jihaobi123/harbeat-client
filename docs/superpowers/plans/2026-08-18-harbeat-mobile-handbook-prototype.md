# HarBeat Mobile Product Handbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one offline HTML file that combines a concise HarBeat mobile product handbook, a clickable nine-view prototype, and front-end annotations.

**Architecture:** Keep maintainable source files under `tools/harbeat-handbook/`, then use a dependency-free Node build script to inline HTML, CSS, content, state logic, and renderers into one distributable file. The browser app uses a small reducer and deterministic mock data; it never calls a network API and can run from `file://`.

**Tech Stack:** HTML5, CSS, vanilla JavaScript, inline SVG, Node.js 22 standard library, Node test runner.

---

## File structure

Create the following focused source tree:

```text
tools/harbeat-handbook/
├── build.mjs                 # Reads source fragments and writes the single HTML bundle
├── src/
│   ├── template.html         # Document shell and build insertion markers
│   ├── styles.css            # Tokens, responsive layout, phone mockups and accessibility
│   ├── content.js            # Handbook copy, mock songs, devices, views and annotations
│   ├── model.js              # Initial state, reducer and selectors
│   ├── render-handbook.js    # Product handbook mode
│   ├── render-prototype.js   # Nine-view clickable prototype
│   ├── render-annotations.js # Front-end annotation mode
│   └── app.js                # Mounting, event delegation and global navigation
└── tests/
    ├── bundle.test.mjs       # Offline bundle and semantic smoke tests
    ├── content.test.cjs      # View, scenario and annotation coverage
    └── model.test.cjs        # Music, device, Pad and reset state transitions

docs/superpowers/specs/
├── 2026-08-18-harbeat-mobile-app-product-design.md
├── 2026-08-18-harbeat-mobile-handbook-prototype-design.md
└── harbeat-mobile-product-handbook.html  # Generated file sent to reviewers
```

The generated HTML is committed because it is the user-facing deliverable. Source files remain committed so later changes are reviewable and reproducible.

## Shared commands

Run all commands from `/Users/jihaobi/Documents/New project`.

```bash
node --test tools/harbeat-handbook/tests/*.test.cjs tools/harbeat-handbook/tests/*.test.mjs
node tools/harbeat-handbook/build.mjs
```

The first command must end with `fail 0`. The second must print the absolute output path and a byte count.

### Task 1: Create the reproducible single-file build

**Files:**

- Create: `tools/harbeat-handbook/build.mjs`
- Create: `tools/harbeat-handbook/src/template.html`
- Create: `tools/harbeat-handbook/src/styles.css`
- Create: `tools/harbeat-handbook/src/content.js`
- Create: `tools/harbeat-handbook/src/model.js`
- Create: `tools/harbeat-handbook/src/render-handbook.js`
- Create: `tools/harbeat-handbook/src/render-prototype.js`
- Create: `tools/harbeat-handbook/src/render-annotations.js`
- Create: `tools/harbeat-handbook/src/app.js`
- Create: `tools/harbeat-handbook/tests/bundle.test.mjs`
- Generate: `docs/superpowers/specs/harbeat-mobile-product-handbook.html`

- [ ] **Step 1: Write the failing bundle test**

Create `bundle.test.mjs` with a test that executes the builder and checks the distributable contract:

```js
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import test from 'node:test';

const testDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(testDir, '../../..');
const buildFile = path.join(repoRoot, 'tools/harbeat-handbook/build.mjs');
const outputFile = path.join(repoRoot, 'docs/superpowers/specs/harbeat-mobile-product-handbook.html');

test('builds a self-contained offline handbook', () => {
  execFileSync(process.execPath, [buildFile], { cwd: repoRoot });
  const html = readFileSync(outputFile, 'utf8');

  assert.match(html, /<!doctype html>/i);
  assert.match(html, /产品手册/);
  assert.match(html, /交互原型/);
  assert.match(html, /前端标注/);
  assert.doesNotMatch(html, /__HB_[A-Z_]+__/);
  assert.doesNotMatch(html, /<(script|link)[^>]+(?:src|href)=["']https?:\/\//i);
});
```

- [ ] **Step 2: Run the test and verify the build does not exist**

Run:

```bash
node --test tools/harbeat-handbook/tests/bundle.test.mjs
```

Expected: FAIL because `tools/harbeat-handbook/build.mjs` does not exist.

- [ ] **Step 3: Add the minimal buildable source shell**

Create `template.html` with exactly five insertion markers:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="HarBeat 移动端产品手册、关键路径原型与前端标注">
  <title>HarBeat 移动端产品手册</title>
  <style>__HB_STYLES__</style>
</head>
<body>
  <a class="skip-link" href="#app">跳到主要内容</a>
  <div id="app" aria-live="polite"></div>
  <script>__HB_CONTENT__</script>
  <script>__HB_MODEL__</script>
  <script>__HB_RENDERERS__</script>
  <script>__HB_APP__</script>
</body>
</html>
```

Create minimal valid source fragments:

```css
:root { color-scheme: light; font-family: Inter, "PingFang SC", system-ui, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; background: #f2efe6; color: #121311; }
.skip-link { position: absolute; left: -9999px; }
.skip-link:focus { left: 12px; top: 12px; z-index: 20; }
```

```js
const HBContent = Object.freeze({ views: {}, scenarios: {}, handbookSections: [], annotations: {} });
globalThis.HBContent = HBContent;
if (typeof module !== 'undefined') module.exports = HBContent;
```

```js
const HBModel = Object.freeze({
  initialState: () => ({ mode: 'handbook', scenario: 'discover', viewId: 'V01' }),
  reduce: (state, action) => action.type === 'RESET' ? HBModel.initialState() : state,
});
globalThis.HBModel = HBModel;
if (typeof module !== 'undefined') module.exports = HBModel;
```

```js
globalThis.HBViews = globalThis.HBViews || {};
globalThis.HBViews.handbook = () => '<main><h1>HarBeat</h1><p>产品手册</p></main>';
```

```js
globalThis.HBViews = globalThis.HBViews || {};
globalThis.HBViews.prototype = () => '<main><h1>交互原型</h1></main>';
```

```js
globalThis.HBViews = globalThis.HBViews || {};
globalThis.HBViews.annotations = () => '<main><h1>前端标注</h1></main>';
```

```js
(() => {
  const root = document.querySelector('#app');
  const state = HBModel.initialState();
  root.innerHTML = [
    '<nav aria-label="显示模式">产品手册 · 交互原型 · 前端标注</nav>',
    HBViews[state.mode](state, HBContent),
  ].join('');
})();
```

Create `build.mjs`:

```js
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const toolRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(toolRoot, '../..');
const src = path.join(toolRoot, 'src');
const output = path.join(repoRoot, 'docs/superpowers/specs/harbeat-mobile-product-handbook.html');

const read = (name) => readFile(path.join(src, name), 'utf8');
const [template, styles, content, model, handbook, prototypeView, annotations, app] = await Promise.all([
  read('template.html'), read('styles.css'), read('content.js'), read('model.js'),
  read('render-handbook.js'), read('render-prototype.js'), read('render-annotations.js'), read('app.js'),
]);

const replacements = {
  __HB_STYLES__: styles,
  __HB_CONTENT__: content,
  __HB_MODEL__: model,
  __HB_RENDERERS__: [handbook, prototypeView, annotations].join('\n'),
  __HB_APP__: app,
};

const html = Object.entries(replacements).reduce(
  (document, [marker, value]) => document.replace(marker, value),
  template,
);

if (/__HB_[A-Z_]+__/.test(html)) throw new Error('Unresolved build marker');
await mkdir(path.dirname(output), { recursive: true });
await writeFile(output, html, 'utf8');
console.log(`${output} ${Buffer.byteLength(html)} bytes`);
```

- [ ] **Step 4: Run the bundle test**

Run:

```bash
node --test tools/harbeat-handbook/tests/bundle.test.mjs
```

Expected: PASS with `tests 1`, `pass 1`, `fail 0`.

- [ ] **Step 5: Commit the scaffold**

```bash
git add tools/harbeat-handbook docs/superpowers/specs/harbeat-mobile-product-handbook.html
git commit -m "feat: scaffold offline HarBeat handbook"
```

### Task 2: Define the handbook content contract

**Files:**

- Modify: `tools/harbeat-handbook/src/content.js`
- Create: `tools/harbeat-handbook/tests/content.test.cjs`

- [ ] **Step 1: Write coverage tests for views and scenarios**

```js
const assert = require('node:assert/strict');
const test = require('node:test');
const content = require('../src/content.js');

test('defines nine unique prototype views', () => {
  assert.deepEqual(Object.keys(content.views), [
    'V01', 'V02', 'V03', 'V04', 'V05', 'V06', 'V07', 'V08', 'V09',
  ]);
  assert.equal(content.views.V01.canonical, 'H01');
  assert.equal(content.views.V02.canonical, 'M01');
  assert.equal(content.views.V09.canonical, 'D02');
});

test('defines three complete scenarios', () => {
  assert.deepEqual(Object.keys(content.scenarios), ['discover', 'import', 'device']);
  for (const scenario of Object.values(content.scenarios)) {
    assert.ok(scenario.steps.length >= 3);
    assert.match(scenario.doneMessage, /完成|已保存|已同步/);
  }
});

test('provides an annotation for every view', () => {
  assert.deepEqual(Object.keys(content.annotations), Object.keys(content.views));
});
```

- [ ] **Step 2: Run the content test and verify failure**

Run:

```bash
node --test tools/harbeat-handbook/tests/content.test.cjs
```

Expected: FAIL because the content object has no views or scenarios.

- [ ] **Step 3: Replace the empty content object with the complete schema**

Use this object shape and these exact identifiers:

```js
const HBContent = Object.freeze({
  meta: {
    product: 'HarBeat', version: '1.0', date: '2026-08-18',
    specFile: '2026-08-18-harbeat-mobile-app-product-design.md',
    dataLabel: '演示数据 / Mock API',
  },
  views: {
    V01: { canonical: 'H01', name: '首页', section: 'home' },
    V02: { canonical: 'M01', name: '音乐 / 推荐', section: 'music' },
    V03: { canonical: 'M01', name: '搜索 / 导入', section: 'music' },
    V04: { canonical: 'M01 子页面', name: '歌曲详情', section: 'music' },
    V05: { canonical: 'M01', name: '曲库 / 歌单', section: 'music' },
    V06: { canonical: 'D01', name: '设备列表', section: 'device' },
    V07: { canonical: 'D01 配对状态', name: '配对', section: 'device' },
    V08: { canonical: 'D01 已连接状态', name: '设备面板', section: 'device' },
    V09: { canonical: 'D02', name: 'Pad 编辑', section: 'device' },
  },
  scenarios: {
    discover: { label: '发现音乐', steps: ['V01', 'V02', 'V04', 'V05'], doneMessage: '音乐已保存到曲库' },
    import: { label: '搜索或导入', steps: ['V02', 'V03', 'V04', 'V05'], doneMessage: '导入结果已保存' },
    device: { label: '配置设备', steps: ['V06', 'V07', 'V08', 'V09', 'V08'], doneMessage: 'Pad 预设已同步' },
  },
  songs: [
    { id: 'trk-electric', title: 'Electric Motion', artist: 'Nova Circuit', style: 'Popping', bpm: 104, key: 'F minor', energy: 82, resource: 'available' },
    { id: 'trk-lock', title: 'Lock It Down', artist: 'Pocket Theory', style: 'Locking', bpm: 110, key: 'A minor', energy: 76, resource: 'available' },
    { id: 'trk-midnight', title: 'After Midnight', artist: 'Velvet Transit', style: 'Hip-Hop', bpm: 96, key: 'D minor', energy: 64, resource: 'metadata_only' },
  ],
  playlists: [
    { id: 'pl-practice', name: '本周练习', trackIds: [] },
    { id: 'pl-battle', name: 'Battle Warm-up', trackIds: ['trk-lock'] },
  ],
  devices: [
    { id: 'rk-stage-01', name: 'HarBeat Stage 01', host: '192.168.31.88', online: true, presetVersion: 3 },
    { id: 'rk-practice-02', name: 'Practice Room 02', host: '192.168.31.52', online: false, presetVersion: 1 },
  ],
  pads: Array.from({ length: 8 }, (_, index) => ({ id: `pad-${index + 1}`, label: `Pad ${index + 1}`, sound: index < 3 ? ['Air Horn', 'Crowd Up', 'Hit'][index] : null })),
  handbookSections: ['定位', '系统职责', '目标用户', '信息架构', '关键流程', 'P0 边界', '协作清单'],
  annotations: {
    V01: {
      purpose: '汇总最近内容、设备状态和推荐入口',
      entry: '用户完成登录或从底部导航进入首页',
      primaryAction: '进入音乐推荐或设备页面',
      states: ['loading', 'ready', 'empty', 'error', 'offline'],
      data: ['Mock HomeSummary', 'Mock DeviceSummary', 'Mock RecommendationRail'],
      events: ['home_recommendation_opened', 'home_device_opened'],
      acceptance: ['无设备时仍可进入音乐功能', '设备摘要与 D01 状态一致'],
    },
    V02: {
      purpose: '根据舞种偏好和个人行为展示推荐音乐',
      entry: '从首页推荐卡或音乐 Tab 进入',
      primaryAction: '选择歌曲并进入详情试听',
      states: ['loading', 'ready', 'empty', 'error', 'offline'],
      data: ['Mock RecommendationSection[]', 'Mock TrackSummary[]'],
      events: ['recommendation_impression', 'recommendation_track_opened'],
      acceptance: ['活动 Session 行为不写入个人画像', '每首歌曲显示舞种与 BPM'],
    },
    V03: {
      purpose: '统一处理站内搜索、外部链接和本地文件导入',
      entry: '从音乐页搜索框或导入按钮进入',
      primaryAction: '选择合法可用的匹配结果',
      states: ['idle', 'loading', 'results', 'empty', 'error', 'offline'],
      data: ['示例 SearchRequest', '示例 ImportSource', 'Mock MatchResult[]'],
      events: ['music_search_submitted', 'external_link_parsed', 'local_file_selected'],
      acceptance: ['来源始终可见', '链接解析不承诺未经授权下载', '失败原因可以区分'],
    },
    V04: {
      purpose: '展示歌曲分析、资源状态并完成试听和保存',
      entry: '从推荐、搜索结果或曲库点击歌曲',
      primaryAction: '试听并保存到曲库或歌单',
      states: ['loading', 'available', 'metadata_only', 'unavailable', 'error', 'offline'],
      data: ['Mock TrackDetail', 'Mock AudioAnalysis', '待确认 ResourceAvailability'],
      events: ['track_preview_started', 'save_sheet_opened', 'track_saved'],
      acceptance: ['展示 BPM、调性、能量与段落', '仅元数据资源不能显示为可播放完整音频'],
    },
    V05: {
      purpose: '管理个人曲库与歌单并验证保存结果',
      entry: '从音乐页分区、保存成功反馈或底部导航进入',
      primaryAction: '查看歌曲或把歌曲加入歌单',
      states: ['loading', 'ready', 'empty', 'error', 'offline'],
      data: ['Mock LibraryTrack[]', 'Mock Playlist[]'],
      events: ['library_opened', 'playlist_opened', 'playlist_track_added'],
      acceptance: ['刚保存的歌曲立即出现', '曲库与歌单状态可区分'],
    },
    V06: {
      purpose: '展示最近设备并提供手动局域网地址入口',
      entry: '从设备 Tab 或首页设备卡进入',
      primaryAction: '选择设备或输入局域网地址',
      states: ['loading', 'ready', 'empty', 'error', 'offline'],
      data: ['Mock DeviceSummary[]', '待确认 ManualHostInput'],
      events: ['device_selected', 'manual_host_submitted'],
      acceptance: ['在线和离线设备可区分', '无设备时可以手动输入地址'],
    },
    V07: {
      purpose: '用配对码确认用户正在连接目标 RK3588',
      entry: '从 V06 选择在线设备或提交地址',
      primaryAction: '提交四位配对码',
      states: ['idle', 'submitting', 'invalid_code', 'error', 'offline'],
      data: ['示例 PairingRequest', '待确认 PairingResult'],
      events: ['pairing_code_submitted', 'pairing_succeeded', 'pairing_failed'],
      acceptance: ['错误配对码不会建立连接', '目标设备名称与地址始终可见'],
    },
    V08: {
      purpose: '解释设备连接、资源和 App/设备预设版本状态',
      entry: '配对成功或进入已连接的设备 Tab',
      primaryAction: '进入 Pad 编辑或处理版本差异',
      states: ['connected', 'syncing', 'dirty', 'synced', 'error', 'offline'],
      data: ['Mock DeviceDetail', '待确认 SyncStatus', '待确认 PresetVersion'],
      events: ['device_dashboard_opened', 'sync_requested', 'device_disconnected'],
      acceptance: ['同时显示 App 与设备版本', '掉线后明确说明不可同步'],
    },
    V09: {
      purpose: '编辑八个独立 Pad 槽位并明确同步到设备',
      entry: '从 V08 的 Pad 预设卡进入',
      primaryAction: '保存 App 版本并确认覆盖设备',
      states: ['ready', 'dirty', 'saving', 'syncing', 'synced', 'error', 'offline'],
      data: ['Mock PadSlot[8]', '待确认 PadPreset', '待确认 SyncJob'],
      events: ['pad_sound_assigned', 'preset_saved', 'preset_sync_confirmed'],
      acceptance: ['固定核心按键不可编辑', '同步前显示设备和版本变化', '同步成功后版本一致'],
    },
  },
});

globalThis.HBContent = HBContent;
if (typeof module !== 'undefined') module.exports = HBContent;
```

- [ ] **Step 4: Strengthen the test against empty annotation fields**

Add:

```js
test('annotations contain executable handoff information', () => {
  for (const annotation of Object.values(content.annotations)) {
    assert.ok(annotation.purpose.length > 4);
    assert.ok(annotation.entry.length > 4);
    assert.ok(annotation.primaryAction.length > 2);
    assert.ok(annotation.states.length >= 3);
    assert.ok(annotation.data.length >= 1);
    assert.ok(annotation.events.length >= 1);
    assert.ok(annotation.acceptance.length >= 1);
  }
});
```

- [ ] **Step 5: Run the content tests and commit**

Run:

```bash
node --test tools/harbeat-handbook/tests/content.test.cjs
```

Expected: PASS with `tests 4`, `pass 4`, `fail 0`.

```bash
git add tools/harbeat-handbook/src/content.js tools/harbeat-handbook/tests/content.test.cjs
git commit -m "feat: define HarBeat handbook content model"
```

### Task 3: Implement deterministic prototype state

**Files:**

- Modify: `tools/harbeat-handbook/src/model.js`
- Create: `tools/harbeat-handbook/tests/model.test.cjs`

- [ ] **Step 1: Write reducer tests for the three user journeys**

```js
const assert = require('node:assert/strict');
const test = require('node:test');
const model = require('../src/model.js');

test('saving a track makes it visible in the library', () => {
  const state = model.reduce(model.initialState(), { type: 'SAVE_TRACK', trackId: 'trk-electric', playlistId: 'pl-practice' });
  assert.deepEqual(state.savedTrackIds, ['trk-electric']);
  assert.deepEqual(state.playlistTrackIds['pl-practice'], ['trk-electric']);
  assert.equal(state.toast, '已保存到「本周练习」');
});

test('editing a pad creates an unsynced app version', () => {
  const state = model.reduce(model.initialState(), { type: 'EDIT_PAD', padId: 'pad-4', sound: 'Scratch Stop' });
  assert.equal(state.padSlots[3].sound, 'Scratch Stop');
  assert.equal(state.appPresetVersion, 4);
  assert.equal(state.devicePresetVersion, 3);
  assert.equal(state.syncState, 'dirty');
});

test('sync requires confirmation before versions match', () => {
  const edited = model.reduce(model.initialState(), { type: 'EDIT_PAD', padId: 'pad-4', sound: 'Scratch Stop' });
  const requested = model.reduce(edited, { type: 'REQUEST_SYNC' });
  assert.equal(requested.overlay, 'sync-confirm');
  assert.equal(requested.devicePresetVersion, 3);
  const synced = model.reduce(requested, { type: 'CONFIRM_SYNC' });
  assert.equal(synced.devicePresetVersion, 4);
  assert.equal(synced.syncState, 'synced');
});

test('reset restores a stable demo state', () => {
  const dirty = model.reduce(model.initialState(), { type: 'DISCONNECT_DEVICE' });
  assert.deepEqual(model.reduce(dirty, { type: 'RESET' }), model.initialState());
});
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
node --test tools/harbeat-handbook/tests/model.test.cjs
```

Expected: FAIL because the minimal reducer does not implement these actions.

- [ ] **Step 3: Implement the immutable reducer**

Replace `model.js` with the complete reducer below. Pairing actions are added in Task 7 after their failing tests exist.

```js
const scenarioSteps = Object.freeze({
  discover: ['V01', 'V02', 'V04', 'V05'],
  import: ['V02', 'V03', 'V04', 'V05'],
  device: ['V06', 'V07', 'V08', 'V09', 'V08'],
});

const fallbackPads = () => Array.from({ length: 8 }, (_, index) => ({
  id: `pad-${index + 1}`,
  label: `Pad ${index + 1}`,
  sound: index < 3 ? ['Air Horn', 'Crowd Up', 'Hit'][index] : null,
}));

const content = () => {
  if (globalThis.HBContent) return globalThis.HBContent;
  if (typeof require !== 'undefined') return require('./content.js');
  throw new Error('HBContent is required');
};

const initialState = () => ({
  mode: 'handbook', scenario: 'discover', viewId: 'V01', stepIndex: 0,
  selectedTrackId: 'trk-electric', savedTrackIds: [],
  playlistTrackIds: { 'pl-practice': [], 'pl-battle': ['trk-lock'] },
  selectedPlaylistId: 'pl-practice', previewPlaying: false,
  deviceConnectionState: 'connected', pairingState: 'idle', pairingHost: '',
  appPresetVersion: 3, devicePresetVersion: 3,
  padSlots: (globalThis.HBContent?.pads || fallbackPads()).map((pad) => ({ ...pad })),
  syncState: 'synced', overlay: null, toast: null,
});

const selectedTrack = (state) => content().songs.find((track) => track.id === state.selectedTrackId);
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const reduce = (state, action) => {
  switch (action.type) {
    case 'SET_MODE':
      return { ...state, mode: action.mode, overlay: null };
    case 'SET_SCENARIO': {
      const steps = scenarioSteps[action.scenario];
      return { ...state, scenario: action.scenario, stepIndex: 0, viewId: steps[0], overlay: null, toast: null };
    }
    case 'GO_TO_VIEW': {
      const index = scenarioSteps[state.scenario].indexOf(action.viewId);
      return { ...state, viewId: action.viewId, stepIndex: index >= 0 ? index : state.stepIndex, overlay: null };
    }
    case 'NEXT_STEP': {
      const steps = scenarioSteps[state.scenario];
      const stepIndex = clamp(state.stepIndex + 1, 0, steps.length - 1);
      return { ...state, stepIndex, viewId: steps[stepIndex], overlay: null };
    }
    case 'PREVIOUS_STEP': {
      const steps = scenarioSteps[state.scenario];
      const stepIndex = clamp(state.stepIndex - 1, 0, steps.length - 1);
      return { ...state, stepIndex, viewId: steps[stepIndex], overlay: null };
    }
    case 'SELECT_TRACK':
      return { ...state, selectedTrackId: action.trackId, previewPlaying: false, viewId: 'V04' };
    case 'TOGGLE_PREVIEW':
      return { ...state, previewPlaying: !state.previewPlaying };
    case 'OPEN_SAVE':
      return { ...state, overlay: 'save-track' };
    case 'SAVE_TRACK': {
      const savedTrackIds = [...new Set([...state.savedTrackIds, action.trackId])];
      const current = state.playlistTrackIds[action.playlistId] || [];
      const playlistTrackIds = { ...state.playlistTrackIds, [action.playlistId]: [...new Set([...current, action.trackId])] };
      const playlistName = content().playlists.find((item) => item.id === action.playlistId)?.name || '曲库';
      return { ...state, savedTrackIds, playlistTrackIds, selectedPlaylistId: action.playlistId, overlay: null, toast: `已保存到「${playlistName}」` };
    }
    case 'EDIT_PAD':
      return {
        ...state,
        padSlots: state.padSlots.map((pad) => pad.id === action.padId ? { ...pad, sound: action.sound } : pad),
        appPresetVersion: state.appPresetVersion + 1,
        syncState: 'dirty',
      };
    case 'REQUEST_SYNC':
      return state.deviceConnectionState === 'connected'
        ? { ...state, overlay: 'sync-confirm' }
        : { ...state, overlay: null, toast: '设备未连接，无法同步' };
    case 'CONFIRM_SYNC':
      return state.overlay === 'sync-confirm' && state.deviceConnectionState === 'connected'
        ? { ...state, overlay: null, syncState: 'synced', devicePresetVersion: state.appPresetVersion, toast: 'Pad 预设已同步' }
        : state;
    case 'DISCONNECT_DEVICE':
      return { ...state, deviceConnectionState: 'disconnected', syncState: state.syncState === 'dirty' ? 'dirty' : 'offline', toast: '设备连接已断开' };
    case 'RECONNECT_DEVICE':
      return { ...state, deviceConnectionState: 'connected', syncState: state.appPresetVersion === state.devicePresetVersion ? 'synced' : 'dirty', toast: '设备已重新连接' };
    case 'CLOSE_OVERLAY':
      return { ...state, overlay: null };
    case 'CLEAR_TOAST':
      return { ...state, toast: null };
    case 'RESET':
      return initialState();
    default:
      return state;
  }
};

const HBModel = Object.freeze({ initialState, reduce, selectedTrack, scenarioSteps });
globalThis.HBModel = HBModel;
if (typeof module !== 'undefined') module.exports = HBModel;
```

- [ ] **Step 4: Run all model tests**

Run:

```bash
node --test tools/harbeat-handbook/tests/model.test.cjs
```

Expected: PASS with `tests 4`, `pass 4`, `fail 0`.

- [ ] **Step 5: Commit the state model**

```bash
git add tools/harbeat-handbook/src/model.js tools/harbeat-handbook/tests/model.test.cjs
git commit -m "feat: add HarBeat prototype state machine"
```

### Task 4: Build the three-mode application shell

**Files:**

- Modify: `tools/harbeat-handbook/src/app.js`
- Modify: `tools/harbeat-handbook/src/styles.css`
- Modify: `tools/harbeat-handbook/tests/bundle.test.mjs`

- [ ] **Step 1: Add shell semantics to the bundle test**

Add assertions:

```js
assert.match(html, /role="tablist"/);
assert.match(html, /data-mode="handbook"/);
assert.match(html, /data-mode="prototype"/);
assert.match(html, /data-mode="annotations"/);
assert.match(html, /data-action="reset"/);
assert.match(html, /aria-label="场景导航"/);
```

- [ ] **Step 2: Run the bundle test and verify failure**

Expected: FAIL on the first missing shell marker.

- [ ] **Step 3: Implement one render loop and delegated events**

In `app.js`, keep one mutable state reference and one render function:

```js
(() => {
  const root = document.querySelector('#app');
  let state = HBModel.initialState();

  const dispatch = (action) => {
    state = HBModel.reduce(state, action);
    render();
  };

  const render = () => {
    const modes = [
      ['handbook', '产品手册'], ['prototype', '交互原型'], ['annotations', '前端标注'],
    ];
    const sidebars = {
      handbook: `<nav class="scenario-nav" aria-label="手册章节">${HBContent.handbookSections.map((section) => `<a href="#${section.id || 'positioning'}">${section.title || section}</a>`).join('')}</nav>`,
      prototype: `<nav class="scenario-nav" aria-label="场景导航">${Object.entries(HBContent.scenarios).map(([id, item]) => `<button data-scenario="${id}" aria-current="${state.scenario === id ? 'page' : 'false'}">${item.label}</button>`).join('')}</nav>`,
      annotations: `<nav class="scenario-nav" aria-label="页面标注导航">${Object.entries(HBContent.views).map(([id, item]) => `<button data-view="${id}" aria-current="${state.viewId === id ? 'page' : 'false'}">${id} · ${item.name}</button>`).join('')}</nav>`,
    };
    root.innerHTML = `
      <header class="app-header">
        <a class="brand" href="#top" aria-label="HarBeat 首页">HARBEAT®</a>
        <div class="mode-tabs" role="tablist" aria-label="显示模式">
          ${modes.map(([id, label]) => `<button role="tab" data-mode="${id}" aria-selected="${state.mode === id}">${label}</button>`).join('')}
        </div>
        <span class="mock-badge">${HBContent.meta.dataLabel}</span>
        <a class="spec-link" href="${HBContent.meta.specFile}">完整规格</a>
        <button class="reset-button" data-action="reset">重置演示</button>
      </header>
      <div class="app-body" id="top">
        ${sidebars[state.mode]}
        <section id="main-panel">${HBViews[state.mode](state, HBContent)}</section>
      </div>`;
  };

  root.addEventListener('click', (event) => {
    const mode = event.target.closest('[data-mode]');
    const scenario = event.target.closest('[data-scenario]');
    const action = event.target.closest('[data-action]');
    if (mode) dispatch({ type: 'SET_MODE', mode: mode.dataset.mode });
    if (scenario) dispatch({ type: 'SET_SCENARIO', scenario: scenario.dataset.scenario });
    if (action?.dataset.action === 'reset') dispatch({ type: 'RESET' });
  });

  globalThis.HBApp = { dispatch, getState: () => structuredClone(state) };
  render();
})();
```

Add the shell layout rules below; Task 9 extends them with the complete visual polish:

```css
:root { --paper:#f2efe6; --ink:#121311; --cobalt:#2457ff; --acid:#dcff32; --signal:#ff4d36; --white:#fff; --line:#d8d5cb; }
.app-header { position: sticky; top: 0; z-index: 10; display: grid; grid-template-columns: auto 1fr auto auto auto; align-items: center; gap: 16px; min-height: 68px; padding: 10px 20px; background: rgba(242,239,230,.96); border-bottom: 1px solid var(--line); }
.brand { color: var(--ink); font-weight: 950; text-decoration: none; letter-spacing: -.04em; }
.mode-tabs { display: flex; justify-content: center; gap: 6px; }
.mode-tabs button, .scenario-nav button, .reset-button { border: 0; border-radius: 10px; padding: 9px 12px; background: transparent; color: var(--ink); cursor: pointer; }
.mode-tabs [aria-selected="true"] { background: var(--ink); color: var(--white); }
.mock-badge { padding: 6px 8px; background: var(--acid); border: 1px solid var(--ink); border-radius: 3px; font-size: 12px; font-weight: 850; }
.app-body { display: grid; grid-template-columns: 190px minmax(0, 1fr); min-height: calc(100vh - 68px); }
.scenario-nav { display: flex; flex-direction: column; gap: 6px; padding: 22px 14px; border-right: 1px solid var(--line); }
.scenario-nav [aria-current="page"] { background: var(--cobalt); color: var(--white); }
#main-panel { min-width: 0; padding: clamp(18px, 4vw, 54px); }
@media (max-width: 760px) { .app-body { grid-template-columns: 1fr; } .scenario-nav { flex-direction: row; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--line); } }
```

- [ ] **Step 4: Run bundle tests and rebuild**

```bash
node --test tools/harbeat-handbook/tests/bundle.test.mjs
node tools/harbeat-handbook/build.mjs
```

Expected: both commands exit 0.

- [ ] **Step 5: Commit the shell**

```bash
git add tools/harbeat-handbook/src/app.js tools/harbeat-handbook/src/styles.css tools/harbeat-handbook/tests/bundle.test.mjs docs/superpowers/specs/harbeat-mobile-product-handbook.html
git commit -m "feat: add handbook mode navigation"
```

### Task 5: Render the concise product handbook

**Files:**

- Modify: `tools/harbeat-handbook/src/content.js`
- Modify: `tools/harbeat-handbook/src/render-handbook.js`
- Modify: `tools/harbeat-handbook/tests/content.test.cjs`

- [ ] **Step 1: Test the required handbook chapters**

Add:

```js
test('handbook covers the approved product narrative', () => {
  assert.deepEqual(content.handbookSections.map((section) => section.id), [
    'positioning', 'system', 'users', 'ia', 'journeys', 'scope', 'handoff',
  ]);
  assert.match(JSON.stringify(content.handbookSections), /RK3588/);
  assert.match(JSON.stringify(content.handbookSections), /个人推荐/);
  assert.match(JSON.stringify(content.handbookSections), /未经授权/);
});
```

- [ ] **Step 2: Run the content test and verify failure**

Expected: FAIL because `handbookSections` is still an array of strings.

- [ ] **Step 3: Add seven concrete handbook section objects**

Replace the string array with these concrete section objects:

```js
handbookSections: [
  {
    id: 'positioning', eyebrow: 'PRODUCT ROLE', title: '手机负责准备，硬件负责稳定执行',
    summary: 'HarBeat App 是音乐内容管理器、个人练习播放器、设备配置器和现场状态解释层。',
    body: '<p>正式活动中，RK3588 负责稳定出声和执行实时音频动作；App 负责找歌、整理曲库、配置 Pad、同步资源和提供备用控制。手机断开后，实体控制器仍能使用已经同步的内容。</p>',
    relatedViewIds: ['V01', 'V08'],
  },
  {
    id: 'system', eyebrow: 'SYSTEM OWNERSHIP', title: '四个部分各自承担清楚的责任',
    summary: 'App 管配置与内容，云端管账号和分析，RK3588 管现场事实，实体控制器管主要操作。',
    body: '<div class="responsibility-grid"><article><b>App</b><span>搜索、试听、曲库、歌单、Pad 编辑和状态显示</span></article><article><b>云端</b><span>账号、元数据、分析任务和个人推荐</span></article><article><b>RK3588</b><span>资源缓存、播放事实、同步版本和实时音频</span></article><article><b>实体控制器</b><span>固定核心按键与八个自定义 Pad 的现场触发</span></article></div>',
    relatedViewIds: ['V06', 'V08', 'V09'],
  },
  {
    id: 'users', eyebrow: 'USERS', title: '组织者与个人舞者共用资产，但不共用画像',
    summary: '组织者或 MC 需要准备和确认现场；个人舞者需要发现、收藏和练习。',
    body: '<p>个人推荐只学习显式舞种偏好和手机端个人行为。活动 Session 的播放、换歌和升降能量不写回个人推荐画像，避免一次活动改变长期口味。</p>',
    relatedViewIds: ['V02', 'V05'],
  },
  {
    id: 'ia', eyebrow: 'INFORMATION ARCHITECTURE', title: '四个底部 Tab，音乐内部集中完成内容任务',
    summary: '常驻导航为首页、音乐、设备、我的；正在使用是临时全屏任务，不是第五个 Tab。',
    body: '<p>音乐页内部依次提供推荐、搜索、曲库和歌单。推荐是默认分区，首页只放轻量推荐入口。设备页负责发现、配对、连接状态和 Pad 预设。</p>',
    relatedViewIds: ['V01', 'V02', 'V03', 'V05', 'V06'],
  },
  {
    id: 'journeys', eyebrow: 'KEY JOURNEYS', title: '三个原型场景都走到可验证的完成状态',
    summary: '发现并保存、搜索或导入、连接设备并同步 Pad。',
    body: '<ol><li>首页 → 推荐 → 歌曲详情 → 保存 → 曲库可见。</li><li>搜索或导入 → 匹配结果 → 保存 → 曲库可见。</li><li>设备列表 → 配对 → 设备面板 → Pad 编辑 → 确认同步 → 版本一致。</li></ol>',
    relatedViewIds: ['V01', 'V03', 'V06'],
  },
  {
    id: 'scope', eyebrow: 'P0 BOUNDARY', title: '手机独立可听歌，连接设备后才承担现场配置',
    summary: '手机独立模式支持搜索、试听、上传、曲库、歌单、推荐和练习播放。',
    body: '<p>App 不承诺专业自动 DJ、Stems 实时处理或低延迟现场音效。QQ 音乐、网易云等外部链接在 P0 只承诺元数据解析和合法资源匹配，不把未经授权的完整音频下载描述为产品能力。</p>',
    relatedViewIds: ['V03', 'V04', 'V08'],
  },
  {
    id: 'handoff', eyebrow: 'TEAM HANDOFF', title: '页面、状态和契约同时交付',
    summary: '产品给目标、流程、状态和验收；后端给对象、错误和事件；前端用 Mock 并行开发。',
    body: '<ul><li>页面必须覆盖加载、空、错误、离线和权限状态。</li><li>接口未确认时显示 Mock 或待确认标签。</li><li>Pad 先保存 App 版本，再由用户明确覆盖 RK3588。</li><li>OpenAPI、WebSocket 事件和状态枚举由前后端共同冻结。</li></ul>',
    relatedViewIds: ['V04', 'V08', 'V09'],
  },
],
```

- [ ] **Step 4: Render the chapters with cross-links**

`render-handbook.js` must return:

```js
globalThis.HBViews = globalThis.HBViews || {};
globalThis.HBViews.handbook = (state, content) => `
  <main class="handbook" tabindex="-1">
    <section class="handbook-hero">
      <span class="zine-sticker">PRODUCT / ${content.meta.version}</span>
      <h1>让舞者找歌，让设备稳定完成现场播放。</h1>
      <p>HarBeat 手机 App 产品手册、关键路径原型与前端交付说明。</p>
      <button data-mode="prototype">开始体验原型</button>
    </section>
    ${content.handbookSections.map((section, index) => `
      <article id="${section.id}" class="handbook-section">
        <p class="eyebrow">${String(index + 1).padStart(2, '0')} / ${section.eyebrow}</p>
        <h2>${section.title}</h2><p>${section.summary}</p>${section.body}
        <div class="related-views">${section.relatedViewIds.map((id) => `<button data-view="${id}" data-mode="prototype">查看 ${id}</button>`).join('')}</div>
      </article>`).join('')}
  </main>`;
```

Extend delegated events in `app.js` so `[data-view]` dispatches `GO_TO_VIEW` before switching mode.

- [ ] **Step 5: Run tests, rebuild and commit**

```bash
node --test tools/harbeat-handbook/tests/content.test.cjs tools/harbeat-handbook/tests/bundle.test.mjs
node tools/harbeat-handbook/build.mjs
git add tools/harbeat-handbook docs/superpowers/specs/harbeat-mobile-product-handbook.html
git commit -m "feat: add concise HarBeat product handbook"
```

Expected: all tests pass and the generated file contains all seven chapter IDs.

### Task 6: Implement the two music journeys

**Files:**

- Modify: `tools/harbeat-handbook/src/render-prototype.js`
- Modify: `tools/harbeat-handbook/src/app.js`
- Modify: `tools/harbeat-handbook/src/styles.css`
- Modify: `tools/harbeat-handbook/tests/model.test.cjs`

- [ ] **Step 1: Add navigation and resource-state tests**

Add tests that assert:

```js
test('discover scenario follows V01 V02 V04 V05', () => {
  let state = model.reduce(model.initialState(), { type: 'SET_SCENARIO', scenario: 'discover' });
  assert.equal(state.viewId, 'V01');
  state = model.reduce(state, { type: 'NEXT_STEP' });
  assert.equal(state.viewId, 'V02');
  state = model.reduce(state, { type: 'NEXT_STEP' });
  assert.equal(state.viewId, 'V04');
  state = model.reduce(state, { type: 'NEXT_STEP' });
  assert.equal(state.viewId, 'V05');
});

test('metadata-only tracks cannot be marked as locally available', () => {
  const state = model.reduce(model.initialState(), { type: 'SELECT_TRACK', trackId: 'trk-midnight' });
  assert.equal(model.selectedTrack(state).resource, 'metadata_only');
});
```

- [ ] **Step 2: Run the model test and verify failure**

Expected: FAIL until scenario transitions and `selectedTrack` are implemented.

- [ ] **Step 3: Render V01 through V05 with one reusable phone shell**

Implement these pure render functions in `render-prototype.js`:

```js
const musicRenderers = {
  V01: renderHome,
  V02: renderRecommendations,
  V03: renderSearchImport,
  V04: renderTrackDetail,
  V05: renderLibrary,
};
```

Each renderer returns real HarBeat labels and mock content from `HBContent`. Required interactions:

- V01: open Recommendation or Device.
- V02: select a track, search, or open Library.
- V03: switch between Search, External Link and Local File; choose a mock result.
- V04: start/stop the visual-only preview, open save overlay, and show `available` or `metadata_only` resource status.
- V05: switch between Library and Playlists and display saved state.

The reusable phone shell contains status bar, current page name, bottom navigation, mini player and scenario step controls.

- [ ] **Step 4: Wire music actions**

Add delegated handlers for:

```text
data-view
data-track
data-action="open-save"
data-action="save-track"
data-action="toggle-preview"
data-action="next-step"
data-action="previous-step"
data-action="close-overlay"
```

Saving uses `SAVE_TRACK`; it must update V05 immediately without persistence or network access.

- [ ] **Step 5: Run tests, rebuild and commit**

```bash
node --test tools/harbeat-handbook/tests/model.test.cjs tools/harbeat-handbook/tests/bundle.test.mjs
node tools/harbeat-handbook/build.mjs
git add tools/harbeat-handbook docs/superpowers/specs/harbeat-mobile-product-handbook.html
git commit -m "feat: add HarBeat music prototype journeys"
```

### Task 7: Implement device pairing, Pad editing and sync

**Files:**

- Modify: `tools/harbeat-handbook/src/render-prototype.js`
- Modify: `tools/harbeat-handbook/src/app.js`
- Modify: `tools/harbeat-handbook/src/styles.css`
- Modify: `tools/harbeat-handbook/tests/model.test.cjs`

- [ ] **Step 1: Add device transition tests**

```js
test('pairing connects the selected RK device', () => {
  let state = model.reduce(model.initialState(), { type: 'DISCONNECT_DEVICE' });
  state = model.reduce(state, { type: 'START_PAIRING', host: '192.168.31.88' });
  assert.equal(state.pairingState, 'enter-code');
  state = model.reduce(state, { type: 'SUBMIT_PAIRING_CODE', code: '3588' });
  assert.equal(state.deviceConnectionState, 'connected');
  assert.equal(state.viewId, 'V08');
});

test('sync is blocked while the device is disconnected', () => {
  let state = model.reduce(model.initialState(), { type: 'EDIT_PAD', padId: 'pad-4', sound: 'Scratch Stop' });
  state = model.reduce(state, { type: 'DISCONNECT_DEVICE' });
  state = model.reduce(state, { type: 'REQUEST_SYNC' });
  assert.equal(state.overlay, null);
  assert.match(state.toast, /设备未连接/);
});
```

- [ ] **Step 2: Run the model test and verify failure**

Expected: FAIL because pairing actions are not implemented.

- [ ] **Step 3: Extend the reducer with pairing actions**

Insert these cases before `CLOSE_OVERLAY`. The demo accepts only code `3588`:

```js
case 'START_PAIRING':
  return {
    ...state,
    pairingHost: action.host,
    pairingState: 'enter-code',
    deviceConnectionState: 'connecting',
    viewId: 'V07',
    toast: null,
  };
case 'SUBMIT_PAIRING_CODE':
  return action.code === '3588'
    ? {
        ...state,
        pairingState: 'paired',
        deviceConnectionState: 'connected',
        viewId: 'V08',
        stepIndex: 2,
        toast: 'HarBeat Stage 01 已连接',
      }
    : {
        ...state,
        pairingState: 'invalid-code',
        deviceConnectionState: 'disconnected',
        toast: '配对码不正确，请重新输入',
      };
```

- [ ] **Step 4: Render V06 through V09**

Add renderers:

```js
const deviceRenderers = {
  V06: renderDeviceList,
  V07: renderPairing,
  V08: renderDeviceDashboard,
  V09: renderPadEditor,
};
```

Required interactions:

- V06: recent-device cards and manual host entry preset to `192.168.31.88`.
- V07: four-digit pairing input with visible demo code helper.
- V08: connection, latency, App preset version, device preset version, sync status and a Disconnect demo action.
- V09: eight Pad slots, four mock sounds, unsaved/saved/synced states, and explicit sync confirmation.
- B01: a persistent device-disconnected banner appears when connection state is not `connected`.
- O02: the confirmation states the device name and version change before allowing overwrite.

- [ ] **Step 5: Run tests, rebuild and commit**

```bash
node --test tools/harbeat-handbook/tests/model.test.cjs tools/harbeat-handbook/tests/bundle.test.mjs
node tools/harbeat-handbook/build.mjs
git add tools/harbeat-handbook docs/superpowers/specs/harbeat-mobile-product-handbook.html
git commit -m "feat: add HarBeat device and Pad prototype"
```

### Task 8: Implement front-end annotations

**Files:**

- Modify: `tools/harbeat-handbook/src/content.js`
- Modify: `tools/harbeat-handbook/src/render-annotations.js`
- Modify: `tools/harbeat-handbook/src/app.js`
- Modify: `tools/harbeat-handbook/src/styles.css`
- Modify: `tools/harbeat-handbook/tests/content.test.cjs`

- [ ] **Step 1: Add annotation vocabulary checks**

```js
test('every view declares its contract maturity', () => {
  const serialized = JSON.stringify(content.annotations);
  assert.match(serialized, /loading/);
  assert.match(serialized, /offline/);
  assert.match(serialized, /acceptance/);
  for (const annotation of Object.values(content.annotations)) {
    assert.match(annotation.contractStatus, /Mock|待确认/);
  }
});
```

- [ ] **Step 2: Run the test and verify failure if labels are missing**

Expected: FAIL because `contractStatus` is not present yet.

- [ ] **Step 3: Render split-view annotations**

Add these exact maturity labels after the `HBContent` declaration and before assigning it to `globalThis`:

```js
const contractStatuses = {
  V01: 'Mock API',
  V02: 'Mock API',
  V03: '待确认：搜索与导入 API',
  V04: '待确认：资源可用性 API',
  V05: 'Mock API',
  V06: '待确认：设备发现 API',
  V07: '待确认：RK 配对 API',
  V08: '待确认：设备状态与 WebSocket 事件',
  V09: '待确认：PadPreset 与 SyncJob',
};
for (const [viewId, contractStatus] of Object.entries(contractStatuses)) {
  HBContent.annotations[viewId].contractStatus = contractStatus;
}
```

`render-annotations.js` returns the current phone screen on the left and a semantic definition list on the right:

```js
globalThis.HBViews = globalThis.HBViews || {};
globalThis.HBViews.annotations = (state, content) => {
  const view = content.views[state.viewId];
  const note = content.annotations[state.viewId];
  return `<main class="annotation-workbench">
    <section class="annotation-phone">${HBViews.prototype(state, content, { embedded: true })}</section>
    <aside class="annotation-panel" aria-label="${state.viewId} 前端标注">
      <p class="eyebrow">${state.viewId} → ${view.canonical}</p><h1>${view.name}</h1>
      <p class="contract-status">${note.contractStatus}</p>
      <dl>
        <dt>页面目的</dt><dd>${note.purpose}</dd>
        <dt>进入条件</dt><dd>${note.entry}</dd>
        <dt>主要操作</dt><dd>${note.primaryAction}</dd>
        <dt>页面状态</dt><dd>${note.states.map((item) => `<code>${item}</code>`).join(' ')}</dd>
        <dt>数据</dt><dd>${note.data.map((item) => `<code>${item}</code>`).join(' ')}</dd>
        <dt>事件</dt><dd>${note.events.map((item) => `<code>${item}</code>`).join(' ')}</dd>
        <dt>验收</dt><dd><ul>${note.acceptance.map((item) => `<li>${item}</li>`).join('')}</ul></dd>
      </dl>
    </aside>
  </main>`;
};
```

Add a compact V01–V09 view selector so engineers can jump directly between annotations.

- [ ] **Step 4: Run tests, rebuild and commit**

```bash
node --test tools/harbeat-handbook/tests/content.test.cjs tools/harbeat-handbook/tests/bundle.test.mjs
node tools/harbeat-handbook/build.mjs
git add tools/harbeat-handbook docs/superpowers/specs/harbeat-mobile-product-handbook.html
git commit -m "feat: add HarBeat front-end annotations"
```

### Task 9: Apply the approved visual system and accessibility behavior

**Files:**

- Modify: `tools/harbeat-handbook/src/styles.css`
- Modify: `tools/harbeat-handbook/src/template.html`
- Modify: `tools/harbeat-handbook/tests/bundle.test.mjs`

- [ ] **Step 1: Add static accessibility and offline checks**

Add:

```js
assert.match(html, /lang="zh-CN"/);
assert.match(html, /class="skip-link"/);
assert.match(html, /:focus-visible/);
assert.match(html, /prefers-reduced-motion/);
assert.doesNotMatch(html, /@import\s+url/);
assert.doesNotMatch(html, /fetch\s*\(/);
assert.doesNotMatch(html, /new\s+WebSocket/);
```

- [ ] **Step 2: Run the bundle test and verify the missing CSS rules fail**

Expected: FAIL on `:focus-visible` or `prefers-reduced-motion`.

- [ ] **Step 3: Complete the C-plus-B visual system**

Define these tokens in `:root`:

```css
:root {
  --paper: #f2efe6; --ink: #121311; --cobalt: #2457ff;
  --acid: #dcff32; --signal: #ff4d36; --white: #ffffff;
  --muted: #74746d; --line: #d8d5cb; --radius-card: 18px;
  --shadow-card: 0 12px 32px rgba(18, 19, 17, .10);
}
```

Apply the design rules:

- Product content uses Paper background, White cards and generous spacing.
- Primary actions and selected navigation use Cobalt.
- Online/success and zine stickers use Acid with an Ink border.
- Signal Red is reserved for warning, high-emphasis Pad and limited editorial accents.
- Editorial covers may use hard borders, offset shadows and at most `rotate(-2deg)`.
- Inputs, device cards, sync confirmation and error notices remain level and regular.
- System fonts only; no font URL or external image URL.

Add keyboard and motion rules:

```css
button:focus-visible, a:focus-visible, input:focus-visible { outline: 3px solid var(--cobalt); outline-offset: 3px; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important; } }
@media (max-width: 900px) { .annotation-workbench { grid-template-columns: 1fr; } .scenario-nav { overflow-x: auto; } }
@media (max-width: 640px) { .app-header { grid-template-columns: 1fr auto; } .mode-tabs { grid-column: 1 / -1; overflow-x: auto; } }
```

- [ ] **Step 4: Run all automated tests and rebuild**

```bash
node --test tools/harbeat-handbook/tests/*.test.cjs tools/harbeat-handbook/tests/*.test.mjs
node tools/harbeat-handbook/build.mjs
```

Expected: all tests pass; the output contains no external dependency.

- [ ] **Step 5: Commit the visual system**

```bash
git add tools/harbeat-handbook docs/superpowers/specs/harbeat-mobile-product-handbook.html
git commit -m "style: apply HarBeat handbook visual system"
```

### Task 10: Verify the final handoff and connect the documents

**Files:**

- Modify: `docs/superpowers/specs/2026-08-18-harbeat-mobile-app-product-design.md`
- Modify: `docs/superpowers/specs/2026-08-18-harbeat-mobile-handbook-prototype-design.md`
- Verify: `docs/superpowers/specs/harbeat-mobile-product-handbook.html`

- [ ] **Step 1: Run the complete automated suite**

```bash
node --test tools/harbeat-handbook/tests/*.test.cjs tools/harbeat-handbook/tests/*.test.mjs
node tools/harbeat-handbook/build.mjs
git diff --check
```

Expected: Node reports `fail 0`; build exits 0; `git diff --check` prints no errors.

- [ ] **Step 2: Verify the bundle from `file://`**

Open `/Users/jihaobi/Documents/New project/docs/superpowers/specs/harbeat-mobile-product-handbook.html` directly in Chrome and Safari with networking disabled. Check:

1. Product Handbook, Prototype and Front-end Annotations all switch without a reload.
2. Discovery ends with `trk-electric` visible in V05.
3. Import shows resource source and the metadata-only limitation.
4. Device scenario accepts code `3588`, edits Pad 4, asks before overwrite and ends with matching versions.
5. Disconnecting shows B01 and blocks sync.
6. Reset restores the original songs, Pad slots, versions and first scenario.
7. Tab and Shift+Tab reach every primary control with visible focus.
8. At 768 px, annotations move below the phone without horizontal page overflow.

- [ ] **Step 3: Verify there are no external resources**

Run:

```bash
rg -n 'https?://|<link[^>]+stylesheet|<script[^>]+src=|fetch\(|WebSocket' docs/superpowers/specs/harbeat-mobile-product-handbook.html
```

Expected: no output. Product copy should name platforms such as QQ 音乐 or网易云 without embedding their URLs.

- [ ] **Step 4: Add reciprocal document links**

At the top of both Markdown specifications, add a relative link to `harbeat-mobile-product-handbook.html` labelled “离线产品手册与交互原型”. Keep the existing version and status metadata intact.

- [ ] **Step 5: Final review and commit**

Review `git diff --stat` and `git status --short`. Stage only the handbook source, tests, generated HTML and the two linked specifications.

```bash
git add tools/harbeat-handbook docs/superpowers/specs/harbeat-mobile-product-handbook.html docs/superpowers/specs/2026-08-18-harbeat-mobile-app-product-design.md docs/superpowers/specs/2026-08-18-harbeat-mobile-handbook-prototype-design.md
git commit -m "docs: deliver HarBeat mobile product handbook"
```

Expected: the commit contains no App, backend, Flutter, iOS or unrelated workspace changes.
