const assert = require('node:assert/strict');
const test = require('node:test');
const content = require('../src/content.js');
const model = require('../src/model.js');

globalThis.HBViews = {};
require('../src/render-prototype.js');

test('music prototype renders a navigable phone shell', () => {
  const html = globalThis.HBViews.prototype(model.initialState(), content);
  assert.match(html, /class="phone-shell"/);
  assert.match(html, /data-view="V02"/);
  assert.match(html, /首页/);
});

test('track detail explains metadata-only resources', () => {
  const state = model.reduce(model.initialState(), { type: 'SELECT_TRACK', trackId: 'trk-midnight' });
  const html = globalThis.HBViews.prototype(state, content);
  assert.match(html, /仅元数据/);
  assert.match(html, /After Midnight/);
});

test('library reflects a saved track', () => {
  let state = model.reduce(model.initialState(), { type: 'SAVE_TRACK', trackId: 'trk-electric', playlistId: 'pl-practice' });
  state = model.reduce(state, { type: 'GO_TO_VIEW', viewId: 'V05' });
  const html = globalThis.HBViews.prototype(state, content);
  assert.match(html, /Electric Motion/);
  assert.match(html, /本周练习/);
});
