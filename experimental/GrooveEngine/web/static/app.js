const state = { library: [], selectedMix: [] };
const libraryEl = document.getElementById('track-library');
const mixSelectionEl = document.getElementById('mix-selection');
const mixResultEl = document.getElementById('mix-result');
const planResultEl = document.getElementById('plan-result');
const strategyRulesEl = document.getElementById('strategy-rules');
const statusBannerEl = document.getElementById('status-banner');

function formatTime(seconds) { const v = Number(seconds || 0); const m = Math.floor(v / 60); const s = (v % 60).toFixed(1).padStart(4, '0'); return `${m}:${s}`; }
function uniqueLibrary() { const map = new Map(); state.library.forEach(track => map.set(track.track_id, track)); state.library = [...map.values()]; }
function updateStatus(text, isEmpty = false) { statusBannerEl.classList.toggle('empty', isEmpty); statusBannerEl.textContent = text; }

function renderLibrary() {
  uniqueLibrary();
  const eligible = state.library.filter(track => track.renderable && (track.bar_structure || []).length > 0);
  libraryEl.className = eligible.length ? 'library-list' : 'library-list empty';
  libraryEl.innerHTML = eligible.length ? eligible.map(track => `
    <div class="library-card">
      <strong>${track.title}</strong>
      <span>${track.artist || track.source}</span>
      <span>bpm ${track.bpm ? Number(track.bpm).toFixed(2) : 'pending'} · ${track.phrase_segments.length} sections</span>
    </div>`).join('') : 'No renderable songs loaded yet.';

  mixSelectionEl.className = eligible.length ? 'library-list' : 'library-list empty';
  mixSelectionEl.innerHTML = eligible.length ? eligible.map(track => `
    <label class="select-card">
      <input type="checkbox" value="${track.track_id}" ${state.selectedMix.includes(track.track_id) ? 'checked' : ''}>
      <div><strong>${track.title}</strong><span>${track.artist || track.source}</span><span>${track.bar_structure.length} bars ready</span></div>
    </label>`).join('') : 'No eligible songs yet.';

  mixSelectionEl.querySelectorAll('input[type="checkbox"]').forEach(input => input.addEventListener('change', () => {
    state.selectedMix = [...mixSelectionEl.querySelectorAll('input[type="checkbox"]:checked')].map(box => box.value);
  }));
}

async function postAnalyze(formData) {
  const response = await fetch('/api/analyze', { method: 'POST', body: formData });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Analyze failed');
  state.library.push(data); renderLibrary(); updateStatus(`Loaded ${state.library.length} songs. Ready for automatic sequencing.`);
}

async function loadStrategyRules() {
  const response = await fetch('/api/dj-strategy'); const data = await response.json();
  strategyRulesEl.innerHTML = `<h3>Internal DJ Logic</h3><ul>${(data.article_takeaways || []).map(item => `<li>${item}</li>`).join('')}</ul>`;
}

async function previewPlan() {
  if (state.selectedMix.length < 2) { planResultEl.classList.remove('empty'); planResultEl.textContent = 'Select at least two real songs first.'; return; }
  planResultEl.classList.remove('empty'); planResultEl.textContent = 'Planning automatic order...';
  const response = await fetch('/api/playlist-plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ track_ids: state.selectedMix }) });
  const data = await response.json();
  if (!response.ok) { planResultEl.textContent = data.error || 'Auto sequence planning failed.'; return; }
  planResultEl.innerHTML = `
    <h3>Auto Sequence Ready</h3>
    <p><strong>order:</strong> ${data.ordered_titles.join(' → ')}</p>
    <p><strong>average score:</strong> ${Number(data.average_score).toFixed(3)}</p>
    <div class="table-wrap"><table><thead><tr><th>Track Flow</th><th>Strategy</th><th>Bars</th><th>Score</th></tr></thead><tbody>${data.transitions.map(item => `<tr><td>${item.track_a_id} → ${item.track_b_id}</td><td>${item.plan.strategy}</td><td>${item.plan.track_a_exit_bar} → ${item.plan.track_b_entry_bar}</td><td>${Number(item.plan.score_breakdown.total_score).toFixed(3)}</td></tr>`).join('')}</tbody></table></div>
    <p>${data.notes.join(' · ')}</p>`;
}

async function buildMix() {
  if (state.selectedMix.length < 2) { mixResultEl.classList.remove('empty'); mixResultEl.textContent = 'Select at least two real songs first.'; return; }
  mixResultEl.classList.remove('empty'); mixResultEl.textContent = 'Rendering automatic mix...';
  const response = await fetch('/api/mix', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ track_ids: state.selectedMix }) });
  const data = await response.json();
  if (!response.ok) { mixResultEl.textContent = data.error || 'Automatic mix render failed.'; return; }
  mixResultEl.innerHTML = `
    <h3>Automatic Mix Ready</h3>
    <p><strong>selected order:</strong> ${data.ordered_titles.join(' → ')}</p>
    <p><strong>duration:</strong> ${formatTime(data.duration_seconds)} · <strong>average transition score:</strong> ${Number(data.average_score).toFixed(3)}</p>
    <audio controls src="${data.audio_url}"></audio>
    <p><a href="${data.audio_url}" target="_blank">Open output file</a></p>
    <div class="table-wrap"><table><thead><tr><th>Track Flow</th><th>Strategy</th><th>Phrase Window</th><th>Score</th></tr></thead><tbody>${data.transitions.map(item => `<tr><td>${item.track_a} → ${item.track_b}</td><td>${item.strategy}</td><td>${item.track_a_exit_phrase} @ ${item.track_a_exit_bar} → ${item.track_b_entry_phrase} @ ${item.track_b_entry_bar}</td><td>${Number(item.score || 0).toFixed(3)}</td></tr>`).join('')}</tbody></table></div>
    <p>${data.playlist_notes.join(' · ')}</p>`;
}

document.getElementById('upload-form').addEventListener('submit', async event => {
  event.preventDefault(); const files = [...event.currentTarget.querySelector('input[type="file"]').files]; if (!files.length) return;
  updateStatus(`Analyzing ${files.length} uploaded song(s)...`, false);
  for (const file of files) { const formData = new FormData(); formData.append('source', 'upload'); formData.append('audio', file); await postAnalyze(formData); }
});

document.getElementById('preview-plan').addEventListener('click', previewPlan);
document.getElementById('build-mix').addEventListener('click', buildMix);
loadStrategyRules(); renderLibrary();
