import math
POLICY={'version':'metric-mix-v1.0','status':'provisional-engineering-rules','minimumMargin':4,'combinationMargin':6,'audibleDbfs':-45,'minimumOverlap':.25,'tempoRatio':[.95,1.05],'beatToleranceMs':65,'maximumDuration':32,'tailQuietSeconds':.25,'maximumCandidatePeak':.98,'scope':'Rule scores are ranking heuristics,not probabilities or calibrated listening accuracy.'}
NAMES={'original':'原渐混','bass':'独立贝斯交接','filter':'旋律滤波','yield':'旋律让位','vocal':'人声唱完再退出','bass_filter':'贝斯交接＋旋律滤波'}

def choose_method(metrics,stats=None):
 stats=stats or {}
 for k in ['bassOverlap','otherOverlap','bassDifference','otherDifference','vocalBenefit']:
  v=metrics.get(k)
  if v is not None and (not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1):raise ValueError('Invalid metric: '+k)
 available=metrics.get('stemAvailable') or {};methods={}
 def add(k,eligible,benefit,cost,reason):
  s=stats.get(k,{});p=stats.get('original',{});penalty=0
  if s.get('peak',0)>POLICY['maximumCandidatePeak'] and k!='original':eligible=False;reason+='；峰值余量不足'
  for field in ['maximumBlockJumpDb','maximumBlockDropDb']:
   delta=s.get(field,0)-p.get(field,0);penalty+=max(0,delta-1.5)*3
  methods[k]={'name':NAMES[k],'eligible':bool(eligible),'score':round(50+benefit-cost-penalty,2) if eligible else None,'benefit':round(benefit,2),'processingCost':cost,'levelPenalty':round(penalty,2),'reason':reason,'status':'candidate' if eligible else 'excluded'}
 def present(key):return metrics.get(key) is not None
 bass=all(present(k) for k in ['bassOverlap','bassDifference']) and available.get('bass',False) and metrics['bassOverlap']>=.25
 other=all(present(k) for k in ['otherOverlap','otherDifference']) and available.get('other',False) and metrics['otherOverlap']>=.25
 bg=28*metrics['bassOverlap']+12*metrics['bassDifference'] if bass else 0
 fg=24*metrics['otherOverlap']+8*metrics['otherDifference'] if other else 0
 add('original',True,0,0,'原方案参照；没有足够新增收益时优先保留')
 add('bass',bass,bg,6,'贝斯同时可闻及音高分布差异代理达到候选门槛' if bass else '贝斯证据缺失、声部不可用或同时可闻程度不足')
 add('filter',other,fg,4,'other同时可闻程度达到门槛；只处理末小节' if other else 'other证据缺失、声部不可用或重叠不足')
 y=other and metrics['otherOverlap']>=.45 and metrics['otherDifference']>=.65
 add('yield',y,30*metrics['otherOverlap']+14*metrics['otherDifference'] if y else 0,11,'较强other重叠及音高分布差异，生成提前退出候选' if y else '未达到旋律提前退出的较高门槛')
 voice=available.get('vocals',False) and metrics.get('vocalSafe') is True and present('vocalBenefit') and metrics['vocalBenefit']>=.2
 add('vocal',voice,30*metrics['vocalBenefit'] if voice else 0,6,'声学尾部、后续空隙及B人声进入检查通过' if voice else '缺少安全的人声尾部/空隙，或保留人声收益不足')
 add('bass_filter',bass and other,bg+fg,12,'贝斯与other均满足门槛；还需胜过较好单项至少6分' if bass and other else '两个单项并未同时满足门槛')
 combo=methods['bass_filter'];singles=[methods[k]['score'] for k in ['bass','filter'] if methods[k]['eligible']]
 if combo['eligible'] and (len(singles)!=2 or combo['score']-max(singles)<POLICY['combinationMargin']):combo.update(eligible=False,status='excluded',reason=combo['reason']+'；没有达到组合额外收益门槛')
 complexity={'original':0,'filter':1,'bass':1,'yield':1,'vocal':1,'bass_filter':2}
 eligible=[k for k,v in methods.items() if v['eligible']];best=min(eligible,key=lambda k:(-methods[k]['score'],complexity[k],k))
 if best!='original' and methods[best]['score']-methods['original']['score']<POLICY['minimumMargin']:best='original'
 return {'policy':POLICY,'recommended':best,'methods':methods,'explanation':methods[best]['reason'],'limitations':['规则阈值尚未通过大样本听感校准','音高分布差异不等于和弦冲突，RMS不等于感知响度','缺失值保持未知；歌曲风格和曲名不触发手法']}
