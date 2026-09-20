import { describe, expect, it } from 'vitest'
import { flatten, series, sourceDocuments, discoverTimelines, differences } from './data'

describe('lossless report inspection', () => {
  it('keeps unknown fields and null separate from zero', () => {
    const rows = flatten({ bpm: null, level: 0, novel: { enabled: false } })
    expect(rows).toContainEqual({ path: '/bpm', value: null })
    expect(rows).toContainEqual({ path: '/level', value: 0 })
    expect(rows).toContainEqual({ path: '/novel/enabled', value: false })
  })
  it('does not chart unavailable values as zero', () => {
    expect(series([{ start: .123, value: null }, { start: .456, value: .4 }], 'value')).toEqual([{ time: .456, value: .4 }])
  })
  it('accepts track collections without merging different songs', () => {
    expect(sourceDocuments({'100.wav':{bpm:120}},'batch')[0].documents.core).toEqual({bpm:120})
    expect(sourceDocuments({ '100.wav': { bpm: 120 }, '101.wav': { bpm: 125 } }, 'batch.json')).toHaveLength(2)
    expect(sourceDocuments({ bpm: 120, key_profile: { confidence: .7 } }, 'core.json')).toHaveLength(1)
  })
  it('exposes PANNs bar probabilities without overwriting the instrument source', () => {
    const views = discoverTimelines({panns:{bars:[{start_sec:1,end_sec:2,instrument_probabilities:[{instrument_class:'piano',mean_probability:.8}]}]}})
    expect(views.curves.find(v=>v.title.includes('piano'))?.points).toEqual([{time:1,value:.8}])
  })
})

it('distinguishes missing from null in version comparison',()=>{expect(differences({bpm:null},{bpm:0,key:null})).toEqual([{path:'/bpm',current:null,comparison:0,change:'数值不同'},{path:'/key',current:undefined,comparison:null,change:'仅对照版本'}])})
