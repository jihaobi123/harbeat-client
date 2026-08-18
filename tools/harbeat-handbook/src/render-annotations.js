globalThis.HBViews = globalThis.HBViews || {};

const renderCodeList = (items) => items.map((item) => `<code>${item}</code>`).join(' ');

globalThis.HBViews.annotations = (state, content) => {
  const view = content.views[state.viewId];
  const note = content.annotations[state.viewId];
  return `<main class="annotation-workbench">
    <section class="annotation-phone">${HBViews.prototype(state, content, { embedded: true })}</section>
    <aside class="annotation-panel" aria-label="${state.viewId} 前端标注">
      <p class="eyebrow">${state.viewId} → ${view.canonical}</p>
      <h1>${view.name}</h1>
      <p class="contract-status">${note.contractStatus}</p>
      <dl>
        <dt>页面目的</dt><dd>${note.purpose}</dd>
        <dt>进入条件</dt><dd>${note.entry}</dd>
        <dt>主要操作</dt><dd>${note.primaryAction}</dd>
        <dt>页面状态</dt><dd>${renderCodeList(note.states)}</dd>
        <dt>数据与对象</dt><dd>${renderCodeList(note.data)}</dd>
        <dt>事件与埋点</dt><dd>${renderCodeList(note.events)}</dd>
        <dt>验收</dt><dd><ul>${note.acceptance.map((item) => `<li>${item}</li>`).join('')}</ul></dd>
      </dl>
      <div class="annotation-note"><b>交付规则</b><p>原型负责表达交互和状态；最终字段以 OpenAPI、WebSocket 事件表与共同冻结的枚举为准。</p></div>
    </aside>
  </main>`;
};
