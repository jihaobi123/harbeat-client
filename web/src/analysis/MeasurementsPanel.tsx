import { Report, series, timeLabel } from './data'
import { Curve, Segments } from './Charts'

const number=(v:any,digits=2)=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(digits):'—'
const names:Record<string,string>={core_features:'已有特征补算',chords:'和弦时间轴',measurements:'动态与起音',emotion_summary:'情绪摘要'}
export default function MeasurementsPanel({report,cursor,onSeek,onRun,busy}:{report:Report;cursor:number;onSeek:(time:number)=>void;onRun:(module:string)=>Promise<void>;busy:boolean}) {
 const ext=report.extensions
 const core=ext.core_features?.data||{}
 const d=ext.measurements?.data?.dynamics, onset=ext.measurements?.data?.onsets
 const chords=ext.chords?.data, emotion=ext.emotion_summary?.data
 const duration=report.summary.duration||1
 return <div className="lab-panel"><div className="lab-panel-title"><h2>和弦、动态与情绪摘要</h2><span>独立证据 · 点击时间定位试听</span></div>
  <div className="lab-actions">{Object.entries(names).map(([key,name])=><button key={key} disabled={busy} onClick={()=>onRun(key)}>{name}{ext[key]?.status==='ready'?' · 重算':' · 运行'}</button>)}</div>
  {Object.keys(names).filter(k=>ext[k]&&ext[k].status!=='ready').map(k=><p key={k} className="lab-alert">{names[k]}：{ext[k].reason||ext[k].status}</p>)}
  <h3>已有特征补算</h3><p className="lab-muted">复用原后端函数，保留原有结果。音色统计仍使用中间最多 30 秒；这组历史算法的响度基于单声道分析副本。</p>
  <div className="lab-table-wrap"><table><thead><tr><th>特征组</th><th>状态</th><th>结果摘要</th></tr></thead><tbody>{[
   ['loudness','原有响度',`LUFS ${number(core.loudness?.data?.integrated_lufs)} · 峰均比 ${number(core.loudness?.data?.crest_factor_db)} dB`],
   ['tonality','原有调性',`${core.tonality?.data?.key||'—'} · 调性清晰度 ${number(core.tonality?.data?.tonal_clarity)}`],
   ['timbre','原有音色',`频谱重心 ${number(core.timbre?.data?.spectral_centroid)} Hz · MFCC 均值 ${number(core.timbre?.data?.mfcc_mean)}`],
   ['rhythm','已有拍点统计',`拍间隔标准差 ${number(core.rhythm?.data?.ibi_std,4)} 秒`],
   ['energy','原有能量曲线',`${core.energy?.data?.length||0} 个窗口`],
  ].map(([key,label,value])=><tr key={key}><td>{label}</td><td>{core[key]?.status==='ready'?'已计算':core[key]?.reason||'未提供'}</td><td>{core[key]?.status==='ready'?value:'—'}</td></tr>)}</tbody></table></div>
  <Curve title="补算能量曲线" points={series(core.energy?.data||[],'relative_energy')} duration={duration} cursor={cursor} onSeek={onSeek}/>
  <h3>和弦时间轴</h3><p className="lab-muted">DeepChroma + CRF，识别 24 种大小三和弦。N 表示模型判断无和弦，unknown 表示未覆盖；不提供校准置信度，也不代表两首歌一定能和谐叠加。</p>
  {chords?<><p>{chords.distinct_chords} 种和弦 · 无和弦 {number(chords.no_chord_seconds)} 秒 · 已覆盖 {number(chords.covered_seconds)} 秒</p><Segments title="和弦区间" collapseList segments={chords.segments||[]} duration={duration} onSeek={onSeek}/></>:<p>尚无可用和弦结果。</p>}
  <h3>动态范围与起音密度</h3><p className="lab-muted">使用原采样率和声道测量响度。RMS P95/P5 是相对门限内的能量幅度范围，不是 EBU LRA。起音包含鼓点、乐器和人声攻击音，不等于 BPM。</p>
  <section className="lab-metrics">{[['RMS P95/P5',d?.rms_p95_p5_db,'dB'],['相对静音占比',d?d.relative_silence_ratio*100:null,'%'],['整曲响度',d?.integrated_lufs,'LUFS'],['起音密度',onset?.events_per_minute,'次/分钟']].map(([label,value,unit])=><div key={String(label)}><small>{label}</small><strong>{number(value)}</strong><span>{unit}</span></div>)}</section>
  <Curve title="RMS 电平" points={series(d?.points||[],'rms_dbfs')} duration={duration} cursor={cursor} onSeek={onSeek} unit="dBFS · 静音值为空" maxGapSec={.075}/>
  <Curve title="起音密度变化" points={series(onset?.windows||[],'events_per_minute')} duration={duration} cursor={cursor} onSeek={onSeek} unit="8 秒窗口 · 次/分钟"/>
  <h3>段落响度差</h3><p className="lab-muted">沿用现有段落边界。差值为当前段相对紧邻上一段；有间隔、静音或段落过短时留空。</p>
  <div className="lab-table-wrap"><table><thead><tr><th>段落</th><th>时间</th><th>LUFS</th><th>与前段差值 LU</th><th>RMS dBFS</th><th>与前段差值 dB</th></tr></thead><tbody>{(d?.sections||[]).map((s:any,i:number)=><tr key={i}><td><button onClick={()=>onSeek(s.start)}>{s.label}</button></td><td>{timeLabel(s.start)}–{timeLabel(s.end)}</td><td>{number(s.integrated_lufs)}</td><td>{number(s.delta_lufs)}</td><td>{number(s.rms_dbfs)}</td><td>{number(s.delta_rms_db)}</td></tr>)}</tbody></table></div>
  {!d?.sections?.length&&<p>没有可用的段落响度记录；需要已有段落边界。</p>}
  <h3>情绪摘要</h3><p className="lab-muted">基于已有 DEAM 曲线按时间加权。波动更大不代表更好听；四维审美分数和 AI 解读不参与混音决策。</p>
  {emotion?<><p>曲线覆盖 {number(emotion.coverage_ratio*100)}% · 正负极性切换 {emotion.polarity_switches} 次（跨缺口不计）</p><section className="lab-metrics">{[['愉悦度均值',emotion.valence_mean],['愉悦度范围',emotion.valence_range],['激活度均值',emotion.arousal_mean],['激活度标准差',emotion.arousal_std]].map(([k,v])=><div key={k}><small>{k}</small><strong>{number(v)}</strong></div>)}</section><div className="lab-table-wrap"><table><thead><tr><th>段落</th><th>愉悦度均值</th><th>激活度均值</th><th>覆盖</th></tr></thead><tbody>{(emotion.sections||[]).map((s:any,i:number)=><tr key={i}><td><button onClick={()=>onSeek(s.start)}>{s.label}</button></td><td>{number(s.valence_mean)}</td><td>{number(s.arousal_mean)}</td><td>{number(s.coverage_ratio*100)}%</td></tr>)}</tbody></table></div></>:<p>尚无可用情绪摘要；先运行情绪曲线，再生成摘要。</p>}
 </div>
}
