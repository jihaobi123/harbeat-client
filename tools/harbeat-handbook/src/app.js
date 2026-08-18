(() => {
  const root = document.querySelector('#app');
  const state = HBModel.initialState();
  root.innerHTML = [
    '<nav aria-label="显示模式">产品手册 · 交互原型 · 前端标注</nav>',
    HBViews[state.mode](state, HBContent),
  ].join('');
})();
