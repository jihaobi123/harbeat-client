const scenarioSteps = Object.freeze({
  discover: ['V01', 'V02', 'V04', 'V05'],
  import: ['V02', 'V03', 'V04', 'V05'],
  device: ['V06', 'V07', 'V08', 'V09', 'V08'],
});

const fallbackPads = () => Array.from({ length: 8 }, (_, index) => ({
  id: `pad-${index + 1}`,
  label: `Pad ${index + 1}`,
  sound: index < 3 ? ['Air Horn', 'Crowd Up', 'Hit'][index] : null,
}));

const content = () => {
  if (globalThis.HBContent) return globalThis.HBContent;
  if (typeof require !== 'undefined') return require('./content.js');
  throw new Error('HBContent is required');
};

const initialState = () => ({
  mode: 'handbook',
  scenario: 'discover',
  viewId: 'V01',
  stepIndex: 0,
  selectedTrackId: 'trk-electric',
  savedTrackIds: [],
  playlistTrackIds: { 'pl-practice': [], 'pl-battle': ['trk-lock'], 'pl-late': ['trk-midnight', 'trk-sidewalk'] },
  selectedPlaylistId: 'pl-practice',
  previewPlaying: false,
  importMode: 'search',
  deviceConnectionState: 'connected',
  pairingState: 'idle',
  pairingHost: '',
  appPresetVersion: 3,
  devicePresetVersion: 3,
  padSlots: (globalThis.HBContent?.pads || fallbackPads()).map((pad) => ({ ...pad })),
  syncState: 'synced',
  overlay: null,
  toast: null,
});

const selectedTrack = (state) => content().songs.find((track) => track.id === state.selectedTrackId);
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const reduce = (state, action) => {
  switch (action.type) {
    case 'SET_MODE':
      return { ...state, mode: action.mode, overlay: null };
    case 'SET_SCENARIO': {
      const steps = scenarioSteps[action.scenario];
      return { ...state, scenario: action.scenario, stepIndex: 0, viewId: steps[0], overlay: null, toast: null };
    }
    case 'GO_TO_VIEW': {
      const scenario = ['V06', 'V07', 'V08', 'V09'].includes(action.viewId)
        ? 'device'
        : action.viewId === 'V03'
          ? 'import'
          : state.scenario;
      const index = scenarioSteps[scenario].indexOf(action.viewId);
      return { ...state, scenario, viewId: action.viewId, stepIndex: index >= 0 ? index : state.stepIndex, overlay: null };
    }
    case 'NEXT_STEP': {
      const steps = scenarioSteps[state.scenario];
      const stepIndex = clamp(state.stepIndex + 1, 0, steps.length - 1);
      return { ...state, stepIndex, viewId: steps[stepIndex], overlay: null };
    }
    case 'PREVIOUS_STEP': {
      const steps = scenarioSteps[state.scenario];
      const stepIndex = clamp(state.stepIndex - 1, 0, steps.length - 1);
      return { ...state, stepIndex, viewId: steps[stepIndex], overlay: null };
    }
    case 'SELECT_TRACK':
      return { ...state, selectedTrackId: action.trackId, previewPlaying: false, viewId: 'V04' };
    case 'SET_IMPORT_MODE':
      return { ...state, importMode: action.mode };
    case 'TOGGLE_PREVIEW':
      return { ...state, previewPlaying: !state.previewPlaying };
    case 'OPEN_SAVE':
      return { ...state, overlay: 'save-track' };
    case 'SAVE_TRACK': {
      const savedTrackIds = [...new Set([...state.savedTrackIds, action.trackId])];
      const current = state.playlistTrackIds[action.playlistId] || [];
      const playlistTrackIds = {
        ...state.playlistTrackIds,
        [action.playlistId]: [...new Set([...current, action.trackId])],
      };
      const playlistName = content().playlists.find((item) => item.id === action.playlistId)?.name || '曲库';
      return {
        ...state,
        savedTrackIds,
        playlistTrackIds,
        selectedPlaylistId: action.playlistId,
        overlay: null,
        toast: `已保存到「${playlistName}」`,
      };
    }
    case 'EDIT_PAD':
      return {
        ...state,
        padSlots: state.padSlots.map((pad) => pad.id === action.padId ? { ...pad, sound: action.sound } : pad),
        appPresetVersion: state.appPresetVersion + 1,
        syncState: 'dirty',
      };
    case 'REQUEST_SYNC':
      return state.deviceConnectionState === 'connected'
        ? { ...state, overlay: 'sync-confirm' }
        : { ...state, overlay: null, toast: '设备未连接，无法同步' };
    case 'CONFIRM_SYNC':
      return state.overlay === 'sync-confirm' && state.deviceConnectionState === 'connected'
        ? {
            ...state,
            overlay: null,
            syncState: 'synced',
            devicePresetVersion: state.appPresetVersion,
            toast: 'Pad 预设已同步',
          }
        : state;
    case 'DISCONNECT_DEVICE':
      return {
        ...state,
        deviceConnectionState: 'disconnected',
        syncState: state.syncState === 'dirty' ? 'dirty' : 'offline',
        toast: '设备连接已断开',
      };
    case 'RECONNECT_DEVICE':
      return {
        ...state,
        deviceConnectionState: 'connected',
        syncState: state.appPresetVersion === state.devicePresetVersion ? 'synced' : 'dirty',
        toast: '设备已重新连接',
      };
    case 'START_PAIRING':
      return {
        ...state,
        scenario: 'device',
        stepIndex: 1,
        pairingHost: action.host,
        pairingState: 'enter-code',
        deviceConnectionState: 'connecting',
        viewId: 'V07',
        toast: null,
      };
    case 'SUBMIT_PAIRING_CODE':
      return action.code === '3588'
        ? {
            ...state,
            scenario: 'device',
            pairingState: 'paired',
            deviceConnectionState: 'connected',
            viewId: 'V08',
            stepIndex: 2,
            toast: 'HarBeat Stage 01 已连接',
          }
        : {
            ...state,
            pairingState: 'invalid-code',
            deviceConnectionState: 'disconnected',
            toast: '配对码不正确，请重新输入',
          };
    case 'CLOSE_OVERLAY':
      return { ...state, overlay: null };
    case 'CLEAR_TOAST':
      return { ...state, toast: null };
    case 'RESET':
      return initialState();
    default:
      return state;
  }
};

const HBModel = Object.freeze({ initialState, reduce, selectedTrack, scenarioSteps });
globalThis.HBModel = HBModel;
if (typeof module !== 'undefined') module.exports = HBModel;
