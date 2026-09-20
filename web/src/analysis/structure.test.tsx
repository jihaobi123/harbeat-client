import { renderToStaticMarkup } from 'react-dom/server'
import { describe,it,expect } from 'vitest'
import StructurePanel, { structureSources } from './StructurePanel'
import { Report } from './data'

const sample=()=>({documents:{core:{phrase_map:[{start:0,end:60,label:'intro'}]},'songformer-sections':{status:'ready',segments:[{start:0,end:12,label:'intro'},{start:12,end:60,label:'chorus',label_confidence:.8}]},'edm-structure':{status:'ready',deployment_status:'shadow',segments:[{start_sec:0,end_sec:60,edmformer_label_candidate:'drop'}]}},timeline:{sections:[{start:0,end:60,label:'intro'}]},audio:{duration:60},summary:{duration:60}} as unknown as Report)
describe('structure source presentation',()=>{
 it('shows verified ready model outputs alongside original heuristic without rewriting it',()=>{
  const report=sample(),before=JSON.stringify(report)
  const html=renderToStaticMarkup(<StructurePanel report={report} onSeek={()=>{}} />)
  expect(html).toContain('SongFormer');expect(html).toContain('副歌');expect(html).toContain('EDM');expect(html).toContain('旧规则')
  expect(JSON.stringify(report)).toBe(before)
  expect(structureSources(report)[0].segments[1].label).toBe('chorus')
 })
 it('does not promote failed or unverified source segments',()=>{
  const report=sample();report.documents['songformer-sections'].status='failed';delete report.documents['edm-structure']
  report.documents.unverified_sidecars={sources:{'songformer-sections':{status:'ready',segments:[{start:0,end:60,label:'chorus'}]}}}
  expect(structureSources(report)).toHaveLength(1)
  expect(structureSources(report)[0].kind).toBe('legacy')
 })
 it('recognizes published NAS structures and keeps model name',()=>{
  const report=sample();report.documents={core:{analysis:{sections:{source:'songformer',items:[{start_ms:1000,end_ms:4000,label:'verse'}]}}}}
  const sources=structureSources(report)
  expect(sources[0].title).toContain('SongFormer');expect(sources[0].segments[0].start).toBe(1)
 })
})
