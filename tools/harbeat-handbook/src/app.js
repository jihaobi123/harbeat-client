(() => {
  const root = document.querySelector('#app');
  let state = HBModel.initialState();

  const dispatch = (action) => {
    state = HBModel.reduce(state, action);
    render();
  };

  const render = () => {
    const sidebars = {
      handbook: `<nav class="scenario-nav" aria-label="手册章节">${HBContent.handbookSections.map((section) => `<a href="#${section.id || 'positioning'}">${section.title || section}</a>`).join('')}</nav>`,
      prototype: `<nav class="scenario-nav" aria-label="场景导航">${Object.entries(HBContent.scenarios).map(([id, item]) => `<button data-scenario="${id}" aria-current="${state.scenario === id ? 'page' : 'false'}">${item.label}</button>`).join('')}</nav>`,
      annotations: `<nav class="scenario-nav" aria-label="页面标注导航">${Object.entries(HBContent.views).map(([id, item]) => `<button data-view="${id}" aria-current="${state.viewId === id ? 'page' : 'false'}">${id} · ${item.name}</button>`).join('')}</nav>`,
    };

    root.innerHTML = `
      <header class="app-header">
        <a class="brand" href="#top" aria-label="HarBeat 首页">HARBEAT®</a>
        <div class="mode-tabs" role="tablist" aria-label="显示模式">
          <button role="tab" data-mode="handbook" aria-selected="${state.mode === 'handbook'}">产品手册</button>
          <button role="tab" data-mode="prototype" aria-selected="${state.mode === 'prototype'}">交互原型</button>
          <button role="tab" data-mode="annotations" aria-selected="${state.mode === 'annotations'}">前端标注</button>
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
    const view = event.target.closest('[data-view]');
    const action = event.target.closest('[data-action]');
    const track = event.target.closest('[data-track]');
    const importMode = event.target.closest('[data-import-mode]');
    const saveTrack = event.target.closest('[data-save-track]');
    const startPairing = event.target.closest('[data-start-pairing]');
    const editPad = event.target.closest('[data-edit-pad]');
    if (scenario) dispatch({ type: 'SET_SCENARIO', scenario: scenario.dataset.scenario });
    if (view) dispatch({ type: 'GO_TO_VIEW', viewId: view.dataset.view });
    if (mode) dispatch({ type: 'SET_MODE', mode: mode.dataset.mode });
    if (track) dispatch({ type: 'SELECT_TRACK', trackId: track.dataset.track });
    if (importMode) dispatch({ type: 'SET_IMPORT_MODE', mode: importMode.dataset.importMode });
    if (saveTrack) dispatch({ type: 'SAVE_TRACK', trackId: saveTrack.dataset.saveTrack, playlistId: saveTrack.dataset.playlist });
    if (startPairing) dispatch({ type: 'START_PAIRING', host: startPairing.dataset.startPairing });
    if (editPad) dispatch({ type: 'EDIT_PAD', padId: editPad.dataset.editPad, sound: editPad.dataset.sound });
    const actions = {
      reset: { type: 'RESET' },
      'open-save': { type: 'OPEN_SAVE' },
      'toggle-preview': { type: 'TOGGLE_PREVIEW' },
      'next-step': { type: 'NEXT_STEP' },
      'previous-step': { type: 'PREVIOUS_STEP' },
      'close-overlay': { type: 'CLOSE_OVERLAY' },
      'disconnect-device': { type: 'DISCONNECT_DEVICE' },
      'reconnect-device': { type: 'RECONNECT_DEVICE' },
      'request-sync': { type: 'REQUEST_SYNC' },
      'confirm-sync': { type: 'CONFIRM_SYNC' },
    };
    if (action?.dataset.action === 'pair-manual-host') {
      dispatch({ type: 'START_PAIRING', host: root.querySelector('#manual-host')?.value || '192.168.31.88' });
      return;
    }
    if (action?.dataset.action === 'submit-pairing') {
      dispatch({ type: 'SUBMIT_PAIRING_CODE', code: root.querySelector('#pairing-code')?.value || '' });
      return;
    }
    if (action && actions[action.dataset.action]) dispatch(actions[action.dataset.action]);
  });

  globalThis.HBApp = { dispatch, getState: () => structuredClone(state) };
  render();
})();
