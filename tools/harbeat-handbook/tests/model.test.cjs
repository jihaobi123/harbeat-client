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
