/** Groove DJ — Online Mix Console Controller */
(function () {
  "use strict";

  /* ═══════════════════════════════════════════════════════════════
     State
     ═══════════════════════════════════════════════════════════════ */
  const state = {
    library: [],        // analyzed tracks from /api/library
    queue: [],          // track_ids in play order
    running: false,
    loaded: false,
    paused: false,
    currentIndex: 0,
    logLines: [],
    scanResults: [],    // music/ folder scan result
  };

  /* ═══════════════════════════════════════════════════════════════
     DOM refs
     ═══════════════════════════════════════════════════════════════ */
  function $(s) { return document.querySelector(s); }
  function $$(s) { return document.querySelectorAll(s); }

  const refs = {
    engineStatus:    $('#engine-status'),
    engineStatusTxt: $('#engine-status-text'),
    modeDisplay:     $('#mode-display'),
    modeLetter:      $('#mode-display .mode-letter'),
    modeName:        $('#mode-display .mode-name'),

    btnScan:         $('#btn-scan'),
    btnAnalyzeAll:   $('#btn-analyze-all'),
    scanStatus:      $('#scan-status'),
    libCount:        $('#lib-count'),
    libList:         $('#track-library-mini'),

    queueEl:         $('#playlist-queue'),
    btnLoad:         $('#btn-load-queue'),
    btnClear:        $('#btn-clear-queue'),

    btnPlay:         $('#btn-play'),
    btnPause:        $('#btn-pause'),
    btnStop:         $('#btn-stop'),
    btnManual:       $('#btn-manual'),

    deckATitle:      $('#deck-a-title'),
    deckAMeta:       $('#deck-a-meta'),
    deckABar:        $('#deck-a-bar'),
    deckATime:       $('#deck-a-time'),
    deckAPanel:      $('#deck-a'),
    deckBTitle:      $('#deck-b-title'),
    deckBMeta:       $('#deck-b-meta'),
    deckBBar:        $('#deck-b-bar'),
    deckBTime:       $('#deck-b-time'),
    deckBPanel:      $('#deck-b'),

    xzone:           $('#xzone'),
    xzoneLabel:      $('#xzone-label'),
    xzoneStrategy:   $('#xzone-strategy'),

    strategyGrid:    $('#strategy-grid'),
    strategyActive:  $('#strategy-active'),
    insertSelect:    $('#insert-track-select'),
    btnInsert:       $('#btn-insert'),
    eventLog:        $('#event-log'),
  };

  /* ═══════════════════════════════════════════════════════════════
     Helpers
     ═══════════════════════════════════════════════════════════════ */
  function fmtTime(s) {
    const v = Number(s || 0);
    const m = Math.floor(v / 60);
    const sec = String(Math.floor(v % 60)).padStart(2, '0');
    return `${m}:${sec}`;
  }

  function now() {
    return new Date().toLocaleTimeString('zh-CN', { hour12: false });
  }

  function log(msg, cls) {
    state.logLines.push({ time: now(), msg, cls: cls || 'info' });
    if (state.logLines.length > 200) state.logLines.shift();
    renderLog();
  }

  function renderLog() {
    if (!refs.eventLog) return;
    if (!state.logLines.length) {
      refs.eventLog.innerHTML = '<span class="log-line empty">暂无事件</span>';
      return;
    }
    refs.eventLog.innerHTML = state.logLines.slice(-30).reverse().map(l =>
      `<span class="log-line ${l.cls}">[${l.time}] ${l.msg}</span>`
    ).join('');
    refs.eventLog.scrollTop = 0;
  }

  /* ═══════════════════════════════════════════════════════════════
     Music folder scan & analyze
     ═══════════════════════════════════════════════════════════════ */
  async function scanFolder() {
    if (!refs.scanStatus) return;
    refs.scanStatus.textContent = '正在扫描 music/ 文件夹...';
    refs.scanStatus.className = 'scan-status';
    try {
      const res = await fetch('/api/music/scan');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      state.scanResults = data.files;
      const unanalyzed = data.files.filter(f => !f.analyzed);
      refs.scanStatus.textContent =
        `找到 ${data.total} 个音频文件，${data.files.length - unanalyzed.length} 已分析，${unanalyzed.length} 待分析`;
      refs.scanStatus.className = unanalyzed.length ? 'scan-status' : 'scan-status ok';
      if (unanalyzed.length) {
        refs.btnAnalyzeAll.disabled = false;
        refs.btnAnalyzeAll.textContent = `⚡ 全部分析 (${unanalyzed.length})`;
      } else {
        refs.btnAnalyzeAll.disabled = true;
        refs.btnAnalyzeAll.textContent = '⚡ 全部分析';
      }
      log(`扫描完成: ${data.total} 文件`, 'ok');
    } catch (err) {
      refs.scanStatus.textContent = `扫描失败: ${err.message}`;
      refs.scanStatus.className = 'scan-status error';
      log(`扫描失败: ${err.message}`, 'err');
    }
  }

  async function analyzeAll() {
    if (refs.btnAnalyzeAll) refs.btnAnalyzeAll.disabled = true;
    if (refs.scanStatus) refs.scanStatus.textContent = '正在全部分析中... (可能需要几分钟)';
    log('开始批量分析...', 'info');
    try {
      const res = await fetch('/api/music/analyze-all', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      if (refs.scanStatus) {
        refs.scanStatus.textContent = `分析完成! ${data.analyzed} 成功, ${data.failed} 失败`;
        refs.scanStatus.className = data.failed ? 'scan-status error' : 'scan-status ok';
      }
      log(`批量分析完成: ${data.analyzed} OK, ${data.failed} 失败`, data.failed ? 'warn' : 'ok');
      await refreshLibrary();
      await scanFolder();
    } catch (err) {
      if (refs.scanStatus) { refs.scanStatus.textContent = `分析失败: ${err.message}`; refs.scanStatus.className = 'scan-status error'; }
      log(`分析失败: ${err.message}`, 'err');
    } finally {
      if (refs.btnAnalyzeAll) refs.btnAnalyzeAll.disabled = false;
    }
  }

  /* ═══════════════════════════════════════════════════════════════
     Library
     ═══════════════════════════════════════════════════════════════ */
  async function refreshLibrary() {
    try {
      const res = await fetch('/api/library');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      state.library = (data.tracks || []).filter(t => t.renderable && t.metadata_path);
      renderLibrary();
      updateInsertSelect();
      updateQueueButtons();
    } catch (err) {
      log(`获取曲库失败: ${err.message}`, 'err');
    }
  }

  function renderLibrary() {
    if (!refs.libList) return;
    if (refs.libCount) refs.libCount.textContent = state.library.length;

    if (!state.library.length) {
      refs.libList.innerHTML = '<p class="empty-msg">暂无已分析歌曲，请先扫描并分析</p>';
      return;
    }

    refs.libList.innerHTML = state.library.map(t => {
      const inQueue = state.queue.includes(t.track_id);
      return `<div class="track-row ${inQueue ? 'selected' : ''}" data-id="${t.track_id}" title="${t.title}">
        <span class="track-name">${t.title}</span>
        <span class="track-info">${t.bpm ? Number(t.bpm).toFixed(1) + ' BPM' : ''} · ${fmtTime(t.duration_seconds)}</span>
      </div>`;
    }).join('');

    refs.libList.querySelectorAll('.track-row').forEach(row => {
      row.addEventListener('click', () => toggleQueueTrack(row.dataset.id));
    });
  }

  function toggleQueueTrack(trackId) {
    const idx = state.queue.indexOf(trackId);
    if (idx >= 0) {
      state.queue.splice(idx, 1);
    } else {
      state.queue.push(trackId);
    }
    renderLibrary();
    renderQueue();
    updateQueueButtons();
  }

  /* ═══════════════════════════════════════════════════════════════
     Queue
     ═══════════════════════════════════════════════════════════════ */
  function renderQueue() {
    if (!refs.queueEl) return;
    if (!state.queue.length) {
      refs.queueEl.innerHTML = '<p class="empty-msg">选择曲库中的歌曲拖入队列</p>';
      return;
    }
    refs.queueEl.innerHTML = state.queue.map((id, i) => {
      const track = state.library.find(t => t.track_id === id);
      const name = track ? track.title : id;
      const cls = i === state.currentIndex ? 'current' : i < state.currentIndex ? 'played' : '';
      return `<div class="queue-item ${cls}">
        <span class="q-pos">${String(i + 1).padStart(2, '0')}</span>
        <span class="q-title">${name}</span>
        <span class="q-del" data-index="${i}" title="移除">×</span>
      </div>`;
    }).join('');

    refs.queueEl.querySelectorAll('.q-del').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const idx = Number(btn.dataset.index);
        state.queue.splice(idx, 1);
        renderLibrary();
        renderQueue();
        updateQueueButtons();
      });
    });
  }

  function updateQueueButtons() {
    if (refs.btnLoad) refs.btnLoad.disabled = state.queue.length < 1 || state.running;
    if (refs.btnClear) refs.btnClear.disabled = state.queue.length < 1;
  }

  function clearQueue() {
    state.queue = [];
    state.currentIndex = 0;
    renderLibrary();
    renderQueue();
    updateQueueButtons();
    log('队列已清空', 'info');
  }

  /* ═══════════════════════════════════════════════════════════════
     Load & Playback
     ═══════════════════════════════════════════════════════════════ */
  async function loadQueue() {
    if (!state.queue.length) return;
    log(`正在加载 ${state.queue.length} 首歌曲...`, 'info');
    try {
      const res = await fetch('/api/online/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track_ids: state.queue }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);

      state.loaded = true;
      state.currentIndex = 0;
      refs.btnPlay.disabled = false;
      refs.btnManual.disabled = false;
      renderQueue();
      log(`已加载: ${data.titles.join(' → ')}`, 'ok');
      updateDeckInfo({ active_track: data.titles[0], idle_track: data.titles[1] || null });
      setEngineStatus('paused', '已加载，等待播放');
    } catch (err) {
      log(`加载失败: ${err.message}`, 'err');
    }
  }

  async function doPlay() {
    if (!state.loaded) return;
    try {
      const res = await fetch('/api/online/start', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);

      state.running = true;
      state.paused = false;
      setEngineStatus('playing', '直播中');
      refs.btnPlay.disabled = true;
      refs.btnPause.disabled = false;
      refs.btnStop.disabled = false;
      refs.btnLoad.disabled = true;
      refs.insertSelect.disabled = false;
      refs.btnInsert.disabled = false;
      log('▶ 在线播放开始', 'ok');
      startPolling();
    } catch (err) {
      log(`播放失败: ${err.message}`, 'err');
    }
  }

  async function doPause() {
    try {
      const res = await fetch('/api/online/pause', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);

      state.paused = true;
      setEngineStatus('paused', '已暂停');
      refs.btnPlay.disabled = false;
      refs.btnPause.disabled = true;
      log('⏸ 播放暂停', 'info');
    } catch (err) {
      log(`暂停失败: ${err.message}`, 'err');
    }
  }

  async function doStop() {
    try {
      const res = await fetch('/api/online/stop', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);

      state.running = false;
      state.loaded = false;
      state.paused = false;
      state.currentIndex = 0;
      setEngineStatus('idle', '已停止');
      refs.btnPlay.disabled = false;
      refs.btnPause.disabled = true;
      refs.btnStop.disabled = true;
      refs.btnManual.disabled = true;
      refs.btnLoad.disabled = false;
      refs.insertSelect.disabled = true;
      refs.btnInsert.disabled = true;
      stopPolling();
      resetDecks();
      renderQueue();
      log('⏹ 播放停止', 'info');
    } catch (err) {
      log(`停止失败: ${err.message}`, 'err');
    }
  }

  /* ═══════════════════════════════════════════════════════════════
     Manual transition
     ═══════════════════════════════════════════════════════════════ */
  async function doManual() {
    if (!state.running) return;

    const strategy = getSelectedStrategy();
    if (refs.btnManual) {
      refs.btnManual.classList.add('firing');
      setTimeout(() => refs.btnManual.classList.remove('firing'), 300);
    }

    try {
      const res = await fetch('/api/online/manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      log(`✋ MANUAL 切歌! 策略: ${data.override_strategy}`, 'ok');
    } catch (err) {
      log(`Manual 失败: ${err.message}`, 'err');
    }
  }

  function getSelectedStrategy() {
    const checked = refs.strategyGrid?.querySelector('input:checked');
    return checked ? checked.value : null;
  }

  /* ═══════════════════════════════════════════════════════════════
     Insert track
     ═══════════════════════════════════════════════════════════════ */
  async function doInsert() {
    if (!refs.insertSelect) return;
    const trackId = refs.insertSelect.value;
    if (!trackId) return;
    log(`正在插入歌曲...`, 'info');
    try {
      const res = await fetch('/api/online/insert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track_id: trackId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      log(`✅ 已插入: ${data.track_title} (位置 #${data.position + 1})`, 'ok');
      state.queue = data.titles.map((t, i) => {
        const existing = state.queue[i];
        return existing || data.track_title;
      });
      renderQueue();
    } catch (err) {
      log(`插入失败: ${err.message}`, 'err');
    }
  }

  function updateInsertSelect() {
    if (!refs.insertSelect) return;
    refs.insertSelect.innerHTML = '<option value="">-- 选择一首已分析的歌曲 --</option>' +
      state.library.map(t => `<option value="${t.track_id}">${t.title} (${t.bpm ? Number(t.bpm).toFixed(1) + ' BPM' : '?'})</option>`).join('');
  }

  /* ═══════════════════════════════════════════════════════════════
     Strategy display
     ═══════════════════════════════════════════════════════════════ */
  function initStrategyCards() {
    if (!refs.strategyGrid) return;
    refs.strategyGrid.querySelectorAll('input[type="radio"]').forEach(radio => {
      radio.addEventListener('change', () => {
        updateStrategyDisplay();
      });
    });
    updateStrategyDisplay();
  }

  function updateStrategyDisplay() {
    if (!refs.strategyActive) return;
    const checked = refs.strategyGrid?.querySelector('input:checked');
    if (checked) {
      const label = checked.closest('.strategy-card')?.querySelector('.strategy-desc')?.textContent || checked.value;
      refs.strategyActive.innerHTML = `当前选择: <strong>${label}</strong>（按 MANUAL 后生效）`;
    }
  }

  /* ═══════════════════════════════════════════════════════════════
     Status polling
     ═══════════════════════════════════════════════════════════════ */
  let pollTimer = null;

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(pollStatus, 400);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  async function pollStatus() {
    try {
      const res = await fetch('/api/online/status');
      const s = await res.json();
      if (!s.running) return;
      applyStatus(s);
    } catch (_) { /* ignore transient */ }
  }

  function applyStatus(s) {
    // Mode
    if (s.mode === 'fade_rescue' && refs.modeDisplay) {
      refs.modeDisplay.className = 'mode-display fade';
      if (refs.modeLetter) refs.modeLetter.textContent = 'F';
      if (refs.modeName) refs.modeName.textContent = '降级救援';
    } else if (s.mode === 'manual' && refs.modeDisplay) {
      refs.modeDisplay.className = 'mode-display manual';
      if (refs.modeLetter) refs.modeLetter.textContent = 'M';
      if (refs.modeName) refs.modeName.textContent = '人工模式';
    } else if (refs.modeDisplay) {
      refs.modeDisplay.className = 'mode-display';
      if (refs.modeLetter) refs.modeLetter.textContent = 'A';
      if (refs.modeName) refs.modeName.textContent = '自动模式';
    }

    // Crossfade / transition zone
    if (s.crossfade_active) {
      if (refs.xzone) refs.xzone.className = 'xzone active';
      if (refs.xzoneLabel) refs.xzoneLabel.textContent = '混音中...';
      if (refs.xzoneStrategy) refs.xzoneStrategy.textContent =
        s.crossfade_strategy ? formatStrat(s.crossfade_strategy) : '';
    } else {
      if (refs.xzone) refs.xzone.className = 'xzone';
      if (refs.xzoneLabel) refs.xzoneLabel.textContent = '等待混音';
      if (refs.xzoneStrategy) refs.xzoneStrategy.textContent = '';
    }

    // State-dependent updates
    if (s.paused && state.running && !state.paused) {
      state.paused = true;
      setEngineStatus('paused', '已暂停');
      refs.btnPlay.disabled = false;
      refs.btnPause.disabled = true;
    } else if (!s.paused && state.paused) {
      state.paused = false;
      setEngineStatus('playing', '直播中');
      refs.btnPlay.disabled = true;
      refs.btnPause.disabled = false;
    }

    // Current index
    if (s.current_track_index !== undefined && s.current_track_index !== state.currentIndex) {
      state.currentIndex = s.current_track_index;
      renderQueue();
    }

    updateDeckInfo(s);
  }

  function updateDeckInfo(s) {
    const activeD = s.active_deck === 'A' ? 'a' : 'b';
    const idleD   = s.active_deck === 'A' ? 'b' : 'a';

    // Active deck
    const aPanel = $(`#deck-${activeD}`);
    const iPanel = $(`#deck-${idleD}`);
    if (aPanel) aPanel.classList.remove('idle');
    if (iPanel) iPanel.classList.add('idle');

    // Badges
    const aBadge = aPanel?.querySelector('.deck-badge');
    const iBadge = iPanel?.querySelector('.deck-badge');
    if (aBadge) { aBadge.textContent = '播放中'; aBadge.className = 'deck-badge active-deck'; }
    if (iBadge) { iBadge.textContent = s.idle_loaded ? '待命' : '空闲'; iBadge.className = 'deck-badge idle-deck'; }

    // Titles
    const aTitle = $(`#deck-${activeD}-title`);
    const iTitle = $(`#deck-${idleD}-title`);
    if (aTitle) aTitle.textContent = s.active_track || '---';
    if (iTitle) iTitle.textContent = s.idle_track || '---';

    // Progress
    if (s.active_seconds_remaining !== undefined && s.active_playhead_seconds !== undefined) {
      const total = s.active_seconds_remaining + s.active_playhead_seconds;
      const pct = total > 0 ? Math.min((s.active_playhead_seconds / total) * 100, 100) : 0;
      const bar = $(`#deck-${activeD}-bar`);
      if (bar) bar.style.width = pct.toFixed(1) + '%';
    }

    // Time
    const aTime = $(`#deck-${activeD}-time`);
    if (aTime && s.active_playhead_seconds !== undefined) {
      const total = (s.active_playhead_seconds || 0) + (s.active_seconds_remaining || 0);
      aTime.textContent = `${fmtTime(s.active_playhead_seconds)} / ${fmtTime(total)}`;
    }
  }

  function resetDecks() {
    ['a','b'].forEach(d => {
      const t = $(`#deck-${d}-title`);
      const b = $(`#deck-${d}-bar`);
      const tm = $(`#deck-${d}-time`);
      const p = $(`#deck-${d}`);
      if (t) t.textContent = '---';
      if (b) b.style.width = '0%';
      if (tm) tm.textContent = '--:--';
      if (p) p.classList.toggle('idle', d === 'b');
    });
    if (refs.xzone) refs.xzone.className = 'xzone';
    if (refs.xzoneLabel) refs.xzoneLabel.textContent = '等待混音';
    if (refs.xzoneStrategy) refs.xzoneStrategy.textContent = '';
  }

  function setEngineStatus(cls, text) {
    if (refs.engineStatus) refs.engineStatus.className = 'engine-badge ' + cls;
    if (refs.engineStatusTxt) refs.engineStatusTxt.textContent = text;
  }

  function formatStrat(s) {
    const map = {
      clean_blend: 'Clean Blend', echo_out: 'Echo Out', riser: 'Riser',
      cut_swap: 'Cut Swap', triplet_swap: 'Triplet Swap', melodic_reset: 'Melodic Reset'
    };
    return map[s] || s;
  }

  /* ═══════════════════════════════════════════════════════════════
     Init
     ═══════════════════════════════════════════════════════════════ */
  function bindEvents() {
    refs.btnScan?.addEventListener('click', scanFolder);
    refs.btnAnalyzeAll?.addEventListener('click', analyzeAll);
    refs.btnLoad?.addEventListener('click', loadQueue);
    refs.btnClear?.addEventListener('click', clearQueue);
    refs.btnPlay?.addEventListener('click', doPlay);
    refs.btnPause?.addEventListener('click', doPause);
    refs.btnStop?.addEventListener('click', doStop);
    refs.btnManual?.addEventListener('click', doManual);
    refs.btnInsert?.addEventListener('click', doInsert);
  }

  function init() {
    bindEvents();
    initStrategyCards();
    refreshLibrary();
    scanFolder();
    log('Groove DJ Console 已就绪', 'ok');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
