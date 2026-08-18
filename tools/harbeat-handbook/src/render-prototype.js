globalThis.HBViews = globalThis.HBViews || {};

const resourceLabels = {
  available: ['可试听', 'resource-ok'],
  metadata_only: ['仅元数据', 'resource-warn'],
  unavailable: ['资源不可用', 'resource-off'],
};

const cover = (song, large = false) => `
  <div class="track-cover cover-${song.accent}${large ? ' cover-large' : ''}" aria-hidden="true">
    <span>${song.style.slice(0, 2).toUpperCase()}</span>
  </div>`;

const trackRow = (song, state) => {
  const [resourceLabel, resourceClass] = resourceLabels[song.resource];
  return `<button class="track-row" data-track="${song.id}">
    ${cover(song)}
    <span class="track-copy"><b>${song.title}</b><small>${song.artist} · ${song.style} · ${song.bpm} BPM</small></span>
    <span class="resource-pill ${resourceClass}">${resourceLabel}</span>
    <span class="row-action" aria-hidden="true">›</span>
  </button>`;
};

const renderHome = (state, content) => `
  <div class="phone-page home-page">
    <div class="phone-heading"><div><small>FOR YOUR DANCE / 08.18</small><h2>今晚动起来</h2></div><span class="avatar">HB</span></div>
    <button class="editorial-card" data-view="V02">
      <span class="zine-mini">POPPING · 98–112 BPM</span>
      <b>你的今日<br>训练能量</b><small>12 首精选 · 约 42 分钟</small>
    </button>
    <div class="section-line"><b>继续准备</b><span>最近任务</span></div>
    <button class="device-summary" data-view="V06">
      <span class="status-dot"></span><span><b>HarBeat Stage 01</b><small>已连接 · 预设版本 3</small></span><span>›</span>
    </button>
    <div class="section-line"><b>最近播放</b><button data-view="V05">查看曲库</button></div>
    ${content.songs.slice(0, 2).map((song) => trackRow(song, state)).join('')}
  </div>`;

const renderRecommendations = (state, content) => `
  <div class="phone-page">
    <div class="phone-heading"><div><small>MUSIC / FOR YOU</small><h2>为你的舞步推荐</h2></div><span class="avatar">HB</span></div>
    <div class="music-tabs"><b>推荐</b><button data-view="V03">搜索</button><button data-view="V05">曲库</button></div>
    <div class="recommend-hero"><span class="zine-mini">DAILY SET</span><b>Popping<br>训练能量</b><small>根据你的舞种与个人收藏更新</small></div>
    <div class="section-line"><b>适合今天</b><span>8 首</span></div>
    ${content.songs.slice(0, 5).map((song) => trackRow(song, state)).join('')}
  </div>`;

const renderSearchImport = (state, content) => {
  const intro = {
    search: ['搜索歌曲、艺人或舞种', '示例：Popping 104 BPM'],
    link: ['粘贴外部歌单链接', '只解析元数据并匹配合法资源'],
    file: ['选择手机本地音频', '上传后进行 BPM、调性与段落分析'],
  }[state.importMode];
  return `<div class="phone-page">
    <div class="phone-heading"><div><small>MUSIC / DISCOVER</small><h2>搜索与导入</h2></div></div>
    <div class="source-switch" role="tablist" aria-label="音乐来源">
      <button data-import-mode="search" aria-selected="${state.importMode === 'search'}">搜索</button>
      <button data-import-mode="link" aria-selected="${state.importMode === 'link'}">外部链接</button>
      <button data-import-mode="file" aria-selected="${state.importMode === 'file'}">本地文件</button>
    </div>
    <label class="search-field"><span>${intro[0]}</span><input value="${intro[1]}" aria-label="${intro[0]}" readonly></label>
    ${state.importMode === 'link' ? '<div class="legal-note"><b>资源说明</b><span>QQ 音乐、网易云等链接仅用于元数据解析与合法资源匹配，不提供未经授权下载。</span></div>' : ''}
    <div class="section-line"><b>${state.importMode === 'search' ? '匹配结果' : '演示结果'}</b><span>${content.songs.length} 项</span></div>
    ${content.songs.slice(0, 5).map((song) => trackRow(song, state)).join('')}
  </div>`;
};

const renderSaveOverlay = (state, content, song) => state.overlay === 'save-track' ? `
  <div class="overlay-backdrop">
    <section class="phone-overlay" role="dialog" aria-modal="true" aria-label="保存歌曲">
      <button class="overlay-close" data-action="close-overlay" aria-label="关闭">×</button>
      <span class="eyebrow">SAVE TRACK</span><h3>保存“${song.title}”</h3><p>选择要加入的歌单，歌曲也会进入个人曲库。</p>
      ${content.playlists.map((playlist) => `<button class="playlist-option" data-save-track="${song.id}" data-playlist="${playlist.id}"><span><b>${playlist.name}</b><small>${state.playlistTrackIds[playlist.id]?.length || 0} 首歌曲</small></span><span>＋</span></button>`).join('')}
    </section>
  </div>` : '';

const renderTrackDetail = (state, content) => {
  const song = HBModel.selectedTrack(state);
  const [resourceLabel, resourceClass] = resourceLabels[song.resource];
  const canPreview = song.resource === 'available';
  const resourceCopy = song.resource === 'available'
    ? '已匹配可试听资源，可以在手机端练习。'
    : song.resource === 'metadata_only'
      ? '仅元数据 · 尚未匹配到可播放资源，可先保存并稍后重试。'
      : '资源不可用 · 可以保留歌曲信息，但当前无法播放。';
  return `<div class="phone-page detail-page">
    <button class="back-link" data-view="V02">← 返回推荐</button>
    <div class="detail-cover-wrap">${cover(song, true)}<span class="resource-pill ${resourceClass}">${resourceLabel}</span></div>
    <small>${song.artist} / ${song.style}</small><h2>${song.title}</h2>
    <div class="analysis-grid"><span><small>BPM</small><b>${song.bpm}</b></span><span><small>调性</small><b>${song.key}</b></span><span><small>能量</small><b>${song.energy}</b></span></div>
    <div class="segment-strip" aria-label="歌曲段落"><i></i><i></i><i></i><i></i><i></i></div>
    <div class="resource-copy ${resourceClass}"><b>${resourceLabel}</b><span>${resourceCopy}</span></div>
    <div class="detail-actions"><button class="preview-button" data-action="toggle-preview" ${canPreview ? '' : 'disabled'}>${state.previewPlaying ? '暂停试听' : '试听 30 秒'}</button><button class="save-button" data-action="open-save">＋ 保存</button></div>
    ${renderSaveOverlay(state, content, song)}
  </div>`;
};

const renderLibrary = (state, content) => {
  const savedSongs = content.songs.filter((song) => state.savedTrackIds.includes(song.id));
  const playlist = content.playlists.find((item) => item.id === state.selectedPlaylistId);
  return `<div class="phone-page">
    <div class="phone-heading"><div><small>MY MUSIC</small><h2>曲库与歌单</h2></div><span class="avatar">${state.savedTrackIds.length}</span></div>
    <div class="music-tabs"><b>曲库</b><button>歌单</button><button data-view="V03">导入</button></div>
    <div class="playlist-card"><span class="zine-mini">PLAYLIST</span><b>${playlist.name}</b><small>${state.playlistTrackIds[playlist.id]?.length || 0} 首歌曲 · 最近更新</small></div>
    <div class="section-line"><b>已保存歌曲</b><span>${savedSongs.length} 首</span></div>
    ${savedSongs.length ? savedSongs.map((song) => trackRow(song, state)).join('') : '<div class="empty-state"><b>曲库还是空的</b><span>从推荐或搜索中保存第一首音乐。</span><button data-view="V02">去发现音乐</button></div>'}
  </div>`;
};

const connectionLabel = (state) => ({ connected: '设备在线', connecting: '正在连接', disconnected: '设备离线' }[state.deviceConnectionState] || '状态未知');

const renderDisconnectedBanner = (state) => state.deviceConnectionState === 'disconnected'
  ? '<div class="disconnect-banner"><b>设备连接已断开</b><span>可以继续编辑 App 版本，但恢复连接前不能同步。</span><button data-action="reconnect-device">重新连接</button></div>'
  : '';

const renderDeviceList = (state, content) => `
  <div class="phone-page device-page">
    <div class="phone-heading"><div><small>DEVICE / LOCAL NETWORK</small><h2>连接 HarBeat</h2></div><span class="avatar">RK</span></div>
    <div class="device-intro"><span class="zine-mini">P0 CONNECTION</span><b>选择最近设备，<br>或输入局域网地址</b><small>配对完成后才能同步 Pad 和音乐资源。</small></div>
    <div class="section-line"><b>最近设备</b><span>${content.devices.length} 台</span></div>
    ${content.devices.map((device) => `<button class="device-card ${device.online ? '' : 'is-offline'}" ${device.online ? `data-start-pairing="${device.host}"` : 'disabled'}><span class="status-dot"></span><span><b>${device.name}</b><small>${device.host} · ${device.online ? '局域网在线' : '上次在线于昨天'}</small></span><span>${device.online ? '配对 ›' : '离线'}</span></button>`).join('')}
    <div class="manual-host"><label for="manual-host">手动输入地址</label><div><input id="manual-host" value="192.168.31.88" inputmode="decimal"><button data-action="pair-manual-host">继续</button></div></div>
  </div>`;

const renderPairing = (state) => `
  <div class="phone-page device-page pairing-page">
    <button class="back-link" data-view="V06">← 返回设备列表</button>
    <div class="pair-icon">38<span>58</span></div>
    <small>PAIRING / ${state.pairingHost || '192.168.31.88'}</small><h2>输入设备上的<br>四位配对码</h2>
    <p>配对码可以确认你正在连接目标 RK3588，而不是同一网络中的其他设备。</p>
    <label class="pair-code"><span>演示配对码：3588</span><input id="pairing-code" value="3588" maxlength="4" inputmode="numeric" aria-label="四位配对码"></label>
    ${state.pairingState === 'invalid-code' ? '<div class="inline-error">配对码不正确，请重新输入。</div>' : ''}
    <button class="wide-primary" data-action="submit-pairing">连接 HarBeat Stage 01</button>
  </div>`;

const renderDeviceDashboard = (state, content) => {
  const device = content.devices[0];
  const versionsMatch = state.appPresetVersion === state.devicePresetVersion;
  return `<div class="phone-page device-page">
    ${renderDisconnectedBanner(state)}
    <div class="phone-heading"><div><small>DEVICE / RK3588</small><h2>设备</h2></div><span class="avatar">RK</span></div>
    <div class="device-hero"><div class="online-row"><span class="status-dot"></span><b>${connectionLabel(state)}</b></div><h3>${device.name}</h3><small>${device.host} · ${device.latency} ms 延迟</small><div class="sync-summary"><span><small>App 版本</small><b>v${state.appPresetVersion}</b></span><i>${versionsMatch ? '＝' : '→'}</i><span><small>设备版本</small><b>v${state.devicePresetVersion}</b></span></div></div>
    <div class="state-card"><span><b>${versionsMatch ? '预设已经同步' : 'App 版本较新'}</b><small>${versionsMatch ? '设备可以脱离手机独立工作' : '同步前会再次确认覆盖范围'}</small></span><span class="resource-pill ${versionsMatch ? 'resource-ok' : 'resource-warn'}">${versionsMatch ? '已同步' : '待同步'}</span></div>
    <button class="preset-card" data-view="V09"><span class="preset-number">08</span><span><b>Battle · Round 1</b><small>8 个自定义 Pad 槽位</small></span><span>编辑 ›</span></button>
    <div class="device-actions"><button data-action="${state.deviceConnectionState === 'connected' ? 'disconnect-device' : 'reconnect-device'}">${state.deviceConnectionState === 'connected' ? '模拟设备掉线' : '重新连接设备'}</button><button data-view="V06">更换设备</button></div>
  </div>`;
};

const renderSyncOverlay = (state) => state.overlay === 'sync-confirm' ? `
  <div class="overlay-backdrop"><section class="phone-overlay sync-overlay" role="dialog" aria-modal="true" aria-label="确认覆盖设备预设">
    <button class="overlay-close" data-action="close-overlay" aria-label="关闭">×</button><span class="eyebrow">SYNC TO RK3588</span><h3>同步并覆盖设备？</h3>
    <p>将把 HarBeat Stage 01 的 Pad 预设从 <b>v${state.devicePresetVersion}</b> 更新为 <b>v${state.appPresetVersion}</b>，共 ${state.padSlots.filter((pad) => pad.sound).length} 个已配置音效。</p>
    <div class="sync-warning">同步完成后，手机断开也不会影响实体控制器使用这套预设。</div><button class="wide-primary" data-action="confirm-sync">确认覆盖并同步</button>
  </section></div>` : '';

const renderPadEditor = (state, content) => `
  <div class="phone-page pad-page">
    ${renderDisconnectedBanner(state)}
    <button class="back-link" data-view="V08">← 返回设备</button>
    <div class="phone-heading"><div><small>PAD PRESET / APP v${state.appPresetVersion}</small><h2>Battle · Round 1</h2></div><span class="resource-pill ${state.syncState === 'synced' ? 'resource-ok' : 'resource-warn'}">${state.syncState === 'synced' ? '已同步' : '未同步'}</span></div>
    <div class="fixed-controls"><b>固定核心按键</b><span>播放 / 暂停 · 下一首 · Talk · 撤销</span><small>核心按键不可重新映射</small></div>
    <div class="pad-grid">${state.padSlots.map((pad, index) => {
      const nextSound = content.sounds[(Math.max(0, content.sounds.indexOf(pad.sound)) + 1) % content.sounds.length];
      return `<button class="pad-slot pad-color-${(index % 4) + 1}" data-edit-pad="${pad.id}" data-sound="${nextSound}"><span>${String(index + 1).padStart(2, '0')}</span><b>${pad.sound || '未配置'}</b><small>${pad.sound ? '点击更换音效' : '点击分配音效'}</small></button>`;
    }).join('')}</div>
    <button class="wide-primary sync-button" data-action="request-sync" ${state.syncState === 'synced' ? 'disabled' : ''}>${state.syncState === 'synced' ? '设备版本已一致' : '同步并覆盖到设备'}</button>
    ${renderSyncOverlay(state)}
  </div>`;

const deviceRenderers = { V06: renderDeviceList, V07: renderPairing, V08: renderDeviceDashboard, V09: renderPadEditor };

const musicRenderers = {
  V01: renderHome,
  V02: renderRecommendations,
  V03: renderSearchImport,
  V04: renderTrackDetail,
  V05: renderLibrary,
};

const renderPhoneNav = (state) => `
  <nav class="phone-nav" aria-label="App 底部导航">
    <button data-view="V01" class="${state.viewId === 'V01' ? 'active' : ''}"><b>⌂</b><span>首页</span></button>
    <button data-view="V02" class="${['V02','V03','V04','V05'].includes(state.viewId) ? 'active' : ''}"><b>♫</b><span>音乐</span></button>
    <button data-view="V06" class="${['V06','V07','V08','V09'].includes(state.viewId) ? 'active' : ''}"><b>▣</b><span>设备</span></button>
    <button><b>●</b><span>我的</span></button>
  </nav>`;

const renderStepControls = (state, content) => {
  const scenario = content.scenarios[state.scenario];
  return `<div class="step-controls">
    <button data-action="previous-step" ${state.stepIndex === 0 ? 'disabled' : ''}>← 上一步</button>
    <span>${state.stepIndex + 1} / ${scenario.steps.length} · ${scenario.label}</span>
    <button data-action="next-step" ${state.stepIndex === scenario.steps.length - 1 ? 'disabled' : ''}>下一步 →</button>
  </div>`;
};

globalThis.HBViews.prototype = (state, content, options = {}) => {
  const renderer = musicRenderers[state.viewId] || deviceRenderers[state.viewId];
  const selected = HBModel.selectedTrack(state);
  return `<main class="prototype-workspace ${options.embedded ? 'is-embedded' : ''}">
    ${options.embedded ? '' : `<div class="prototype-heading"><div><p class="eyebrow">CLICKABLE PROTOTYPE</p><h1>${content.views[state.viewId].name}</h1></div><span>${state.viewId} → ${content.views[state.viewId].canonical}</span></div>`}
    <div class="phone-shell">
      <div class="phone-island"></div>
      <div class="phone-screen">${renderer(state, content)}</div>
      ${state.previewPlaying ? `<div class="mini-player">${cover(selected)}<span><b>${selected.title}</b><small>试听片段 · 00:12</small></span><button data-action="toggle-preview">Ⅱ</button></div>` : ''}
      ${renderPhoneNav(state)}
      ${state.toast ? `<div class="toast" role="status">${state.toast}</div>` : ''}
    </div>
    ${options.embedded ? '' : renderStepControls(state, content)}
  </main>`;
};
