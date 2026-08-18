globalThis.HBViews = globalThis.HBViews || {};

globalThis.HBViews.handbook = (state, content) => `
  <main class="handbook" tabindex="-1">
    <section class="handbook-hero">
      <span class="zine-sticker">PRODUCT / ${content.meta.version}</span>
      <p class="eyebrow">MOBILE APP · PRODUCT HANDBOOK</p>
      <h1>让舞者找歌，<br>让设备稳定完成现场播放。</h1>
      <p>HarBeat 手机 App 产品手册、关键路径原型与前端交付说明。</p>
      <div class="hero-actions">
        <button class="primary-button" data-mode="prototype">开始体验原型</button>
        <button class="secondary-button" data-mode="annotations">查看前端标注</button>
      </div>
    </section>
    ${content.handbookSections.map((section, index) => `
      <article id="${section.id}" class="handbook-section">
        <p class="eyebrow">${String(index + 1).padStart(2, '0')} / ${section.eyebrow}</p>
        <h2>${section.title}</h2>
        <p class="section-summary">${section.summary}</p>
        <div class="section-body">${section.body}</div>
        <div class="related-views">
          ${section.relatedViewIds.map((id) => `<button data-view="${id}" data-mode="prototype">查看 ${id}</button>`).join('')}
        </div>
      </article>`).join('')}
  </main>`;
