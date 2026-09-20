import { Row } from './data'

export const dimensionNames: Record<string,string> = {
  stems:'分轨与音轨', vocals:'人声活动', rhythm:'节拍与律动', structure:'歌曲结构',
  instruments:'乐器与鼓组', harmony:'调性与和声', energy:'能量与响度',
  mixing:'混音与转场', style:'曲风与情绪', quality:'质量与来源', other:'其他原始信息',
}
export const audioNames: Record<string,string> = {master:'原曲',vocals:'人声',drums:'鼓',bass:'贝斯',other:'其他伴奏',drum_kick:'底鼓',drum_snare:'军鼓',drum_hihat:'踩镲',drum_tom:'通鼓',drum_cymbal:'镲片'}
export const sourceNames: Record<string,string> = {extension_emotion:'补充情绪曲线',extension_instruments:'补充通用乐器',extension_roughness:'感官粗糙度',extension_repeat:'重复段落聚类',historical_annotations:'历史人工标注',legacy_source_notes:'历史来源说明',source_binding_notes:'来源关联说明',core:'原有主分析',library:'正式曲库详细分析',separated_stem_activity:'真实分轨测量',vocal_activity:'人声活动识别','songformer-sections':'SongFormer 结构','edm-structure':'EDM 结构','instrument-analysis':'PANNs / ADTOF',legacy_spectral_stem_estimate:'历史整曲频谱估算'}

export function dimension(path:string):string {
  if (/extension_instruments/i.test(path))return 'instruments'
  if (/extension_repeat/i.test(path))return 'structure'
  if (/extension_roughness/i.test(path))return 'energy'
  if (/legacy_spectral_stem_estimate|separated_stem_activity|stem_activity|stem_quality|\/stems(?:\/|$)|\/assets\//i.test(path))return 'stems'
  if (/vocal_activity|vocal_events|vocal_density|has_vocals/i.test(path))return 'vocals'
  if (/instrument-analysis|instrument_probabilities|drum_groups|drum_events|drum_summary|panns|adtof/i.test(path))return 'instruments'
  if (/transition|cue|bass_risk|intro_clean|outro_clean|intro_is_clean|outro_is_clean/i.test(path))return 'mixing'
  if (/songformer-sections|edm-structure|sections|phrase_map/i.test(path))return 'structure'
  if (/beat|tempo|bpm|time_signature|groove/i.test(path))return 'rhythm'
  if (/\/key(?:_|\/|$)|chord|tonal|camelot/i.test(path))return 'harmony'
  if (/loudness|energy|spectral|rms|peak|clipping/i.test(path))return 'energy'
  if (/genre|style|dance|mood|emotion/i.test(path))return 'style'
  if (/quality|confidence|warning|status|error|version|fingerprint|hash|producer|pipeline/i.test(path))return 'quality'
  return 'other'
}
export function groupRows(rows:Row[]) {
  const groups=Object.fromEntries(Object.keys(dimensionNames).map(k=>[k,[] as Row[]]))
  rows.forEach(row=>groups[dimension(row.path)].push(row))
  return groups
}
