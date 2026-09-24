export type Interval = [number, number]
export type VocalMapping = {aStart:number; bStart:number; bEnd:number; duration:number; rate:number}
export type OverlapMeasure = {
  weightedOverlap:number; simultaneousSec:number; weightedSec:number; normalizationSec:number;
  aIntervals:Interval[]; bIntervals:Interval[]; collisions:Interval[]; aRows:number[]; bRows:number[];
}
// Preserve V3's source-time padding. The sole new feature is aligned overlap.
function mappedIntervals(source:Interval[]|null, start:number, end:number, rate:number, duration:number) {
  if (!Array.isArray(source)) throw Error('缺少人声活动区间')
  const rows:number[] = [], intervals:Interval[] = []
  source.forEach((interval, index) => {
    if (!Array.isArray(interval) || interval.length !== 2 || !interval.every(Number.isFinite) ||
        interval[0] < 0 || interval[1] <= interval[0]) throw Error('人声活动区间无效')
    const s = Math.max(start, interval[0]-.3), e = Math.min(end, interval[1]+.3)
    if (e > s) {
      rows.push(index+1)
      intervals.push([Math.max(0,(s-start)/rate),Math.min(duration,(e-start)/rate)])
    }
  })
  intervals.sort((a,b) => a[0]-b[0] || a[1]-b[1])
  const merged:Interval[] = []
  for (const [s,e] of intervals) {
    const last = merged.at(-1)
    if (last && s <= last[1]) last[1] = Math.max(last[1],e)
    else merged.push([s,e])
  }
  return {intervals:merged,rows}
}

export function alignedVocalOverlap(a:Interval[]|null, b:Interval[]|null, mapping:VocalMapping):OverlapMeasure {
  const {aStart,bStart,bEnd,duration,rate} = mapping
  if (![aStart,bStart,bEnd,duration,rate].every(Number.isFinite) || aStart < 0 || bStart < 0 ||
      duration <= 0 || rate <= 0 || bEnd <= bStart || Math.abs(bEnd-bStart-duration*rate) > .002)
    throw Error('人声时间映射无效')
  const aa = mappedIntervals(a,aStart,aStart+duration,1,duration)
  const bb = mappedIntervals(b,bStart,bEnd,rate,duration)
  const collisions:Interval[] = []
  let i=0, j=0
  while (i < aa.intervals.length && j < bb.intervals.length) {
    const [as,ae] = aa.intervals[i], [bs,be] = bb.intervals[j]
    const s = Math.max(as,bs), e = Math.min(ae,be)
    if (e > s) collisions.push([s,e])
    if (ae <= be) i++
    else j++
  }
  // Integral of 4*x*(1-x), x=t/duration. Full simultaneous activity scores 1.
  const integral = (t:number) => 2*t*t/duration - 4*t*t*t/(3*duration*duration)
  const simultaneousSec = collisions.reduce((n,[s,e]) => n+e-s,0)
  const weightedSec = collisions.reduce((n,[s,e]) => n+integral(e)-integral(s),0)
  const normalizationSec = 2*duration/3
  return {weightedOverlap:Math.max(0,Math.min(1,weightedSec/normalizationSec)),
    simultaneousSec,weightedSec,normalizationSec,aIntervals:aa.intervals,bIntervals:bb.intervals,
    collisions,aRows:aa.rows,bRows:bb.rows}
}
