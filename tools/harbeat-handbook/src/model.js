const HBModel = Object.freeze({
  initialState: () => ({ mode: 'handbook', scenario: 'discover', viewId: 'V01' }),
  reduce: (state, action) => action.type === 'RESET' ? HBModel.initialState() : state,
});
globalThis.HBModel = HBModel;
if (typeof module !== 'undefined') module.exports = HBModel;
