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

test('provides enough mock music to make recommendations believable', () => {
  assert.ok(content.songs.length >= 8);
  assert.ok(new Set(content.songs.map((song) => song.style)).size >= 3);
  assert.ok(content.songs.some((song) => song.resource === 'metadata_only'));
});

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

test('handbook covers the approved product narrative', () => {
  assert.deepEqual(content.handbookSections.map((section) => section.id), [
    'positioning', 'system', 'users', 'ia', 'journeys', 'scope', 'handoff',
  ]);
  assert.match(JSON.stringify(content.handbookSections), /RK3588/);
  assert.match(JSON.stringify(content.handbookSections), /个人推荐/);
  assert.match(JSON.stringify(content.handbookSections), /未经授权/);
});

test('every view declares its contract maturity', () => {
  const serialized = JSON.stringify(content.annotations);
  assert.match(serialized, /loading/);
  assert.match(serialized, /offline/);
  assert.match(serialized, /acceptance/);
  for (const annotation of Object.values(content.annotations)) {
    assert.match(annotation.contractStatus, /Mock|待确认/);
  }
});
