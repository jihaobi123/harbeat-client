import { Report, series } from './data'
import { Curve } from './Charts'
import { audioNames, sourceNames } from './dimensions'

export default function StemPanel({report,cursor,onSeek,selected,onSelect,onMeasure,busy}:{report:Report;cursor:number;onSeek:(t:number)=>void;selected:string;onSelect:(name:string)=>void;onMeasure:()=>void;busy:boolean}) {
  const assets=report.audio.assets||{}, stems=['vocals','drums','bass','other'],source=report.view_sources?.stems||report.primary_source
  const doc=report.documents[source], real=doc?.method==='separated_audio_rms_p95'
  const hasFiles=stems.some(k=>assets[k]?.id), hasCurves=report.timeline.stems.length>0
  return <section className="lab-panel"><div className="lab-panel-title"><h2>分轨试听与活动曲线</h2><button disabled={!hasFiles||busy} onClick={onMeasure}>{busy?'正在读取音轨…':real?'刷新真实分轨曲线':'读取真实分轨曲线'}</button></div>
    <p className="lab-muted">选择音轨后，顶部播放器会独听该轨。首次使用先准备原曲和四大分轨；就绪后各轨始终同步，切换只改变音量。细分鼓组可在顶部提前准备。</p>
    <div className="lab-audio-grid">{['master',...stems,...Object.keys(assets).filter(k=>k.startsWith('drum_'))].map(k=>{const a=assets[k];return <button key={k} className={selected===k?'selected':''} disabled={!a?.id&&!(k==='master'&&report.audio.sha256)} onClick={()=>onSelect(k)}><b>{audioNames[k]||k}</b><small>{a?.id?`${a.sample_rate?.toLocaleString()} Hz · ${a.channels} 声道`:(k==='master'&&report.audio.sha256)?'已关联原曲':a?.reason||'此来源未关联音轨文件'}</small></button>})}</div>
    {!hasCurves&&<p className="lab-notice">{hasFiles?'真实分轨文件已接入，可直接试听。活动曲线需读取音频后生成，点击上方按钮开始。':'这份历史报告没有真实分轨文件或活动曲线。请选择左侧的「正式曲库」或「NAS 预处理」报告。'}</p>}
    {hasCurves&&<><p className="lab-notice">来源：{sourceNames[source]||source}。{real?'曲线为各分轨相对能量，不是乐器存在概率。':source==='legacy_spectral_stem_estimate'?'这是历史整曲频谱估算，不能当作真实分轨测量。':'按原始来源定义展示，原值完整保留。'}</p>{stems.map(k=>{const points=series(report.timeline.stems,k);return points.length?<Curve key={k} title={`${audioNames[k]} · 分轨活动`} points={points} duration={report.summary.duration||report.audio.duration||1} cursor={cursor} onSeek={onSeek} domain={[0,1]} unit={real?'每轨 P95 归一化 RMS':'来源原始指标'}/>:<p key={k} className="lab-muted">{audioNames[k]}：此来源没有测量记录。</p>})}</>}
    {Object.entries(report.documents).filter(([,v])=>v.stem_quality_profile||v.analysis?.stem_quality_profile).map(([name,v])=><details key={name}><summary>分轨质量与完整性 · {sourceNames[name]||name}</summary><pre>{JSON.stringify((v.analysis||v).stem_quality_profile,null,2)}</pre></details>)}
  </section>
}
