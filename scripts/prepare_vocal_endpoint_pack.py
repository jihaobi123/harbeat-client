"""Build the controlled pack only when actual source-bound detection passes."""
import argparse,hashlib,json,pathlib,shutil

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def validate_handover_sources(c,a,b):
 p=c['plan'];e=a['selected']
 if not e:raise ValueError('actual model rejected probe')
 # Incoming interval is frozen, but model evidence must also not expose strong activity there.
 if any(x['start']<p['window']['end']+.15 and x['tailEnd']>p['window']['start']-.3 for x in b['report']['candidates']+b['report']['rejected']):raise ValueError('incoming model activity requires review')
 if any(t['source'][field]!=c['sourceVerification'][side][field] for side,t in [('a',a),('b',b)] for field in ['vocalSha256','masterSha256','runId','manifestSha256']):raise ValueError('analysis/render source mismatch')

def prepare(root,web):
 probe=root/'probe-talgo';pack=json.loads((probe/'audio/vocal-bed-data.json').read_text());analysis=json.loads((probe/'analysis.json').read_text());original=json.loads((root/'analysis.json').read_text());out=web/'vocal-endpoints-audio';out.mkdir(exist_ok=True)
 for c in pack['cases']:
  a=next(x for x in analysis['contexts'] if x['id']==c['plan']['from']);b=next(x for x in analysis['contexts'] if x['id']==c['plan']['to']);e=a['selected'];p=c['plan']
  validate_handover_sources(c,a,b)
  c['endpoint']={k:round(e[k]-p['start'],9) for k in ['tailEnd','nextOnset','fadeStart','fadeEnd']}
  for key,asset in c['assets'].items():
   src=probe/'audio'/pathlib.Path(asset['url']).name
   if sha(src)!=asset['sha256']:raise ValueError('asset changed')
   shutil.copy2(src,out/src.name);asset['url']='/vocal-endpoints-audio/'+src.name
  context=probe/(a['id']+'.wav')
  if sha(context)!=a['contextSha256']:raise ValueError('context changed')
  shutil.copy2(context,out/context.name)
  c['evidence']=dict(selected=e,contextStart=a['start'],contextUrl='/vocal-endpoints-audio/'+context.name,contextSha256=a['contextSha256'],analysis=a,control=b)
 pack.update(schema='harbeat.vocal-endpoints-pack.v1',selectionSha256=hashlib.sha256((probe/'audio/vocal-bed-data.json').read_bytes()+(probe/'analysis.json').read_bytes()).hexdigest(),
  audit=dict(rejectedIncomingProbe=dict(pair="Doin' It → Tonight",reason='new model found voice in frozen incoming window',evidence=json.loads((root/'probe-tonight-rejected/analysis.json').read_text())),originalContexts=[dict(title=x['title'],selected=x['selected'],rejected=x['report']['rejected'],candidates=x['report']['candidates']) for x in original['contexts']],expandedSelection=pack['audit']),
  limitation='New exploratory pair selected with unchanged automatic cue/vocal gates after all three original outgoing contexts failed endpoint checks. Both current arms freeze this new pair and all other curves. Provisional thresholds; no lyric/semantic or accuracy certification. Original trial untouched.')
 (web/'vocal-endpoints-data.json').write_text(json.dumps(pack,ensure_ascii=False,indent=2)+'\n');(root/'pack.json').write_text(json.dumps(pack,ensure_ascii=False,indent=2)+'\n')
 print('pack',[(c['aTitle'],c['bTitle'],c['endpoint']) for c in pack['cases']])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);p.add_argument('web',type=pathlib.Path);a=p.parse_args();prepare(a.root,a.web)
