const assert = require('node:assert/strict');
const test = require('node:test');
const model = require('../src/model.js');

test('saving a track makes it visible in the library', () => {
  const state = model.reduce(model.initialState(), { type: 'SAVE_TRACK', trackId: 'trk-electric', playlistId: 'pl-practice' });
  assert.deepEqual(state.savedTrackIds, ['trk-electric']);
  assert.deepEqual(state.playlistTrackIds['pl-practice'], ['trk-electric']);
  assert.equal(state.toast, '已保存到「本周练习」');
});

test('editing a pad creates an unsynced app version', () => {
  const state = model.reduce(model.initialState(), { type: 'EDIT_PAD', padId: 'pad-4', sound: 'Scratch Stop' });
  assert.equal(state.padSlots[3].sound, 'Scratch Stop');
  assert.equal(state.appPresetVersion, 4);
  assert.equal(state.devicePresetVersion, 3);
  assert.equal(state.syncState, 'dirty');
});

test('sync requires confirmation before versions match', () => {
  const edited = model.reduce(model.initialState(), { type: 'EDIT_PAD', padId: 'pad-4', sound: 'Scratch Stop' });
  const requested = model.reduce(edited, { type: 'REQUEST_SYNC' });
  assert.equal(requested.overlay, 'sync-confirm');
  assert.equal(requested.devicePresetVersion, 3);
  const synced = model.reduce(requested, { type: 'CONFIRM_SYNC' });
  assert.equal(synced.devicePresetVersion, 4);
  assert.equal(synced.syncState, 'synced');
});

test('reset restores a stable demo state', () => {
  const dirty = model.reduce(model.initialState(), { type: 'DISCONNECT_DEVICE' });
  assert.deepEqual(model.reduce(dirty, { type: 'RESET' }), model.initialState());
});

test('discover scenario follows V01 V02 V04 V05', () => {
  let state = model.reduce(model.initialState(), { type: 'SET_SCENARIO', scenario: 'discover' });
  assert.equal(state.viewId, 'V01');
  state = model.reduce(state, { type: 'NEXT_STEP' });
  assert.equal(state.viewId, 'V02');
  state = model.reduce(state, { type: 'NEXT_STEP' });
  assert.equal(state.viewId, 'V04');
  state = model.reduce(state, { type: 'NEXT_STEP' });
  assert.equal(state.viewId, 'V05');
});

test('metadata-only tracks cannot be marked as locally available', () => {
  const state = model.reduce(model.initialState(), { type: 'SELECT_TRACK', trackId: 'trk-midnight' });
  assert.equal(model.selectedTrack(state).resource, 'metadata_only');
});

test('pairing connects the selected RK device', () => {
  let state = model.reduce(model.initialState(), { type: 'DISCONNECT_DEVICE' });
  state = model.reduce(state, { type: 'START_PAIRING', host: '192.168.31.88' });
  assert.equal(state.pairingState, 'enter-code');
  state = model.reduce(state, { type: 'SUBMIT_PAIRING_CODE', code: '3588' });
  assert.equal(state.deviceConnectionState, 'connected');
  assert.equal(state.viewId, 'V08');
});

test('sync is blocked while the device is disconnected', () => {
  let state = model.reduce(model.initialState(), { type: 'EDIT_PAD', padId: 'pad-4', sound: 'Scratch Stop' });
  state = model.reduce(state, { type: 'DISCONNECT_DEVICE' });
  state = model.reduce(state, { type: 'REQUEST_SYNC' });
  assert.equal(state.overlay, null);
  assert.match(state.toast, /设备未连接/);
});

test('direct device navigation selects the device scenario', () => {
  const state = model.reduce(model.initialState(), { type: 'GO_TO_VIEW', viewId: 'V08' });
  assert.equal(state.scenario, 'device');
  assert.equal(state.stepIndex, 2);
});
