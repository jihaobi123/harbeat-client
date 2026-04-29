const state = { library: [], selectedMix: [], lastReport: null, lastPreviewRow: null, tagLog: [], importLog: [] };
const libraryEl = document.getElementById('track-library');
const mixSelectionEl = document.getElementById('mix-selection');
const transitionReportEl = document.getElementById('transition-report');
const statusBannerEl = document.getElementById('status-banner');
const pairSummaryEl = document.getElementById('pair-summary');
const listenResultEl = document.getElementById('listen-result');
const shortlistLimitEl = document.getElementById('shortlist-limit');
const notesEl = document.getElementById('session-notes');
const tagPaletteEl = document.getElementById('tag-palette');
const tagLogEl = document.getElementById('tag-log');
const importLogEl = document.getElementById('import-log');

function formatTime(seconds) {
  const v = Number(seconds || 0);
  const m = Math.floor(v / 60);
  const s = String(Math.floor(v % 60)).padStart(2, '0');
  return `${m}:${s}`;
}

function fmt(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
}

function updateStatus(text, isEmpty = false) {
  if (!statusBannerEl) return;
  statusBannerEl.classList.toggle('empty', isEmpty);
  statusBannerEl.textContent = text;
}

function uniqueLibrary() {
  const map = new Map();
  state.library.forEach(track => map.set(track.track_id, track));
  state.library = [...map.values()];
}

function eligibleTracks() {
  uniqueLibrary();
  return state.library.filter(track => track.renderable && track.metadata_path);
}

function selectedPair() {
  if (state.selectedMix.length < 2) return null;
  return state.selectedMix.slice(0, 2);
}

function renderImportLog() {
  if (!importLogEl) return;
  if (!state.importLog.length) {
    importLogEl.classList.add('empty');
    importLogEl.textContent = '暂无导入日志。';
    return;
  }
  importLogEl.classList.remove('empty');
  importLogEl.innerHTML = state.importLog.slice().reverse().map(item => `
    <div class="import-log-item ${item.status}">
      <strong>${item.file}</strong>
      <span>${item.status}</span>
      <small>${item.message}</small>
    </div>
  `).join('');
}

function pushImportLog(file, status, message) {
  state.importLog.push({ file, status, message });
  renderImportLog();
}

function renderTagLog() {
  if (!tagLogEl) return;
  if (!state.tagLog.length) {
    tagLogEl.classList.add('empty');
    tagLogEl.textContent = '还没有记录任何听感标签。';
    return;
  }
  tagLogEl.classList.remove('empty');
  tagLogEl.innerHTML = state.tagLog.slice().reverse().map(item => `
    <div class="tag-log-item">
      <strong>${item.tag}</strong>
      <span>${item.label}</span>
      <small>${item.note || '无补充备注'}</small>
    </div>
  `).join('');
}

function attachTagPalette() {
  if (!tagPaletteEl) return;
  tagPaletteEl.querySelectorAll('.tag-chip').forEach(button => {
    button.addEventListener('click', () => {
      if (!state.lastPreviewRow) {
        updateStatus('请先试听一个候选，再记录听感标签。', false);
        return;
      }
      const note = notesEl ? notesEl.value.trim() : '';
      state.tagLog.push({
        tag: button.dataset.tag,
        label: candidateMeta(state.lastPreviewRow),
        note,
      });
      renderTagLog();
      updateStatus(`已记录标签：${button.dataset.tag}`, false);
    });
  });
}

function renderLibrary() {
  if (!libraryEl || !mixSelectionEl) return;
  const tracks = eligibleTracks();
  libraryEl.className = tracks.length ? 'library-list test-library' : 'library-list empty';
  libraryEl.innerHTML = tracks.length ? tracks.map(track => `
    <article class="library-card tight-card">
      <strong>${track.title}</strong>
      <span>${track.artist || track.source || 'unknown source'}</span>
      <span>${track.bpm ? `${Number(track.bpm).toFixed(2)} BPM` : 'BPM pending'} · ${formatTime(track.duration_seconds)}</span>
    </article>
  `).join('') : '暂无可试听歌曲。';

  mixSelectionEl.className = tracks.length ? 'library-list test-select-list' : 'library-list empty';
  mixSelectionEl.innerHTML = tracks.length ? tracks.map(track => `
    <label class="select-card tight-select ${state.selectedMix.includes(track.track_id) ? 'active' : ''}">
      <input type="checkbox" value="${track.track_id}" ${state.selectedMix.includes(track.track_id) ? 'checked' : ''}>
      <div>
        <strong>${track.title}</strong>
        <span>${track.artist || track.source || 'unknown source'}</span>
        <span>${track.phrase_segments.length} sections · ${track.bar_structure.length} bars</span>
      </div>
    </label>
  `).join('') : '请选择两首歌进行测试。';

  mixSelectionEl.querySelectorAll('input[type="checkbox"]').forEach(input => {
    input.addEventListener('change', () => {
      const selected = [...mixSelectionEl.querySelectorAll('input[type="checkbox"]:checked')].map(box => box.value).slice(0, 2);
      state.selectedMix = selected;
      renderLibrary();
      renderPairSummary();
    });
  });

  renderPairSummary();
}

function renderPairSummary() {
  if (!pairSummaryEl) return;
  const pair = selectedPair();
  if (!pair) {
    pairSummaryEl.classList.add('empty');
    pairSummaryEl.textContent = '未选择测试对。';
    return;
  }
  const [a, b] = pair.map(id => state.library.find(track => track.track_id === id)).filter(Boolean);
  if (!a || !b) return;
  pairSummaryEl.classList.remove('empty');
  pairSummaryEl.innerHTML = `<strong>${a.title}</strong> → <strong>${b.title}</strong><br><span class="muted">将基于这两首歌生成接歌位置与接歌方法候选。</span>`;
}

async function postAnalyze(file) {
  const formData = new FormData();
  formData.append('source', 'upload');
  formData.append('audio', file);
  pushImportLog(file.name, 'pending', '正在分析音频、结构和元数据...');
  const response = await fetch('/api/analyze', { method: 'POST', body: formData });
  const data = await response.json();
  if (!response.ok) {
    const message = data.error || 'Analyze failed';
    pushImportLog(file.name, 'failed', message);
    throw new Error(message);
  }
  state.library.push(data);
  pushImportLog(file.name, 'success', `导入成功：${data.title || file.name}`);
  renderLibrary();
  updateStatus(`已导入 ${eligibleTracks().length} 首可试听歌曲。`, false);
}

function rowMetrics(row) {
  return `分析 ${fmt(row.analysis_score, 3)} / 验证 ${fmt(row.render_validation_score, 3)} / 最终 ${fmt(row.final_score, 3)}`;
}

function candidateMeta(row) {
  return `${row.strategy} · window ${row.candidate_window} · overlap ${row.overlap_beats} beats`;
}

function renderTransitionReport(data) {
  if (!transitionReportEl) return;
  state.lastReport = data;
  const rows = data.rows || [];
  const winner = data.winner_section?.recommended;
  transitionReportEl.classList.remove('empty');
  transitionReportEl.innerHTML = `
    <div class="report-summary-strip">
      <div><strong>推荐</strong><span>${winner ? candidateMeta(winner) : '暂无'}</span></div>
      <div><strong>分析候选数</strong><span>${data.overview_section?.analysis_candidate_count || rows.length}</span></div>
      <div><strong>真实验证 shortlist</strong><span>${data.overview_section?.render_validation_shortlist_count || 0}</span></div>
      <div><strong>已验证</strong><span>${data.diagnostics_section?.validated_row_count || 0}</span></div>
    </div>
    <div class="candidate-stack">
      ${rows.map((row, index) => `
        <article class="candidate-card ${winner && winner.candidate_rank === row.candidate_rank ? 'candidate-card-winner' : ''}">
          <div class="candidate-topline">
            <div>
              <strong>#${index + 1}</strong>
              <span>${candidateMeta(row)}</span>
            </div>
            <span class="status-pill status-${row.render_validation_status}">${row.render_validation_status}</span>
          </div>
          <div class="candidate-scoreline">
            <strong>${rowMetrics(row)}</strong>
            <span>Δ ${fmt(row.score_delta_after_render, 3)}</span>
          </div>
          <div class="mini-metrics">
            <span>loudness Δ ${fmt(row.render_loudness_delta_db, 2)} dB</span>
            <span>low-band ${fmt(row.render_low_band_conflict, 2)}</span>
            <span>peak ${fmt(row.render_peak_db, 2)} dB</span>
            <span>groove loss ${fmt(row.render_groove_softening_indicator, 2)}</span>
          </div>
          <div class="candidate-actions">
            <button class="chip listen-btn" data-rank="${row.candidate_rank}">试听此接法</button>
          </div>
        </article>
      `).join('')}
    </div>
  `;

  transitionReportEl.querySelectorAll('.listen-btn').forEach(button => {
    button.addEventListener('click', async () => {
      const rank = Number(button.dataset.rank);
      const row = rows.find(item => Number(item.candidate_rank) === rank);
      if (!row) return;
      await renderCandidatePreview(row);
    });
  });
}

async function previewTransitionReport() {
  if (!transitionReportEl) return;
  const pair = selectedPair();
  if (!pair) {
    transitionReportEl.classList.remove('empty');
    transitionReportEl.textContent = '请先选择两首歌。';
    return;
  }
  transitionReportEl.classList.remove('empty');
  transitionReportEl.textContent = '正在生成候选...';
  const response = await fetch('/api/transition-report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ track_a_id: pair[0], track_b_id: pair[1], limit: 8, render_shortlist_limit: Number(shortlistLimitEl ? shortlistLimitEl.value : 3) || 3 })
  });
  const data = await response.json();
  if (!response.ok) {
    transitionReportEl.textContent = data.error || '候选生成失败。';
    return;
  }
  renderTransitionReport(data);
}

async function renderCandidatePreview(row) {
  if (!listenResultEl) return;
  const pair = selectedPair();
  if (!pair) return;
  listenResultEl.classList.remove('empty');
  listenResultEl.textContent = '正在渲染试听音频...';
  const response = await fetch('/api/render-transition-candidate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ track_a_id: pair[0], track_b_id: pair[1], row })
  });
  const data = await response.json();
  if (!response.ok) {
    listenResultEl.textContent = data.error || '试听渲染失败。';
    return;
  }

  state.lastPreviewRow = row;
  const summary = data.summary || {};
  listenResultEl.innerHTML = `
    <div class="listen-summary">
      <strong>${summary.track_a || 'Track A'} → ${summary.track_b || 'Track B'}</strong>
      <span>${summary.strategy || row.strategy} · ${summary.handoff_profile || row.handoff_profile || 'handoff'}</span>
    </div>
    <audio controls src="${data.audio_url}"></audio>
    <div class="mini-metrics listen-metrics">
      <span>exit ${summary.track_a_exit_bar}</span>
      <span>entry ${summary.track_b_entry_bar}</span>
      <span>peak ${fmt(summary.peak_db, 2)} dB</span>
      <span>headroom ${fmt(summary.headroom_db, 2)} dB</span>
      <span>low-band ${fmt(summary.low_band_conflict, 2)}</span>
      <span>transient loss ${fmt(summary.transient_loss_indicator, 2)}</span>
    </div>
    <p class="muted">${(summary.notes || []).slice(0, 4).join(' · ')}</p>
    <p><a href="${data.audio_url}" target="_blank">打开试听音频</a></p>
  `;
  updateStatus(`正在试听：${candidateMeta(row)}`, false);
}

const uploadFormEl = document.getElementById('upload-form');
if (uploadFormEl) {
  uploadFormEl.addEventListener('submit', async event => {
    event.preventDefault();
    const fileInput = event.currentTarget.querySelector('input[type="file"]');
    const files = fileInput ? [...fileInput.files] : [];
    if (!files.length) return;
    updateStatus(`正在导入 ${files.length} 首歌曲... 每首歌可能需要 1-3 分钟。`, false);
    for (const file of files) {
      try {
        await postAnalyze(file);
      } catch (error) {
        updateStatus(`导入失败：${error.message}`, false);
      }
    }
  });
}

const previewTransitionReportButton = document.getElementById('preview-transition-report');
if (previewTransitionReportButton) {
  previewTransitionReportButton.addEventListener('click', previewTransitionReport);
}

attachTagPalette();
renderImportLog();
renderTagLog();
renderLibrary();
