"""Attach archived outputs by the historical sample ID; never promote them to measured stems."""
import argparse
import json
from pathlib import Path
from .store import Store
from .report import build_report


def main():
    p=argparse.ArgumentParser();p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    store=Store(a.output);seen=set();count=0
    sources={f.stem:json.loads(f.read_text()) for f in a.sources.glob('*.json')}
    for item in store.reports():
        audio=item.get('audio') or {};name=audio.get('name','');key=Path(name).stem
        if key not in {'100','101','102','103','106','107','108'} or key in seen or not audio.get('sha256'):continue
        seen.add(key);report=store.get_report(item['id']);docs=report['documents']
        for source,values in sources.items():
            value=values.get(key)
            if not isinstance(value,dict):continue
            label='legacy_spectral_stem_estimate' if source=='jetson_analysis_enriched' else source
            docs[label]=value
        docs['legacy_source_notes']={'binding':'historical_sample_id_reference',
            'note':'归档结果按原工程样本编号关联，归档文件未保存音频指纹；整曲频谱估算的分轨活动不能当作真实分轨测量',
            'source_files':list(sources),'sample_id':key}
        enriched=build_report(docs,report['extensions'],audio);store.save_report(enriched);count+=1
    print('Historical samples updated:',count)


if __name__=='__main__':main()
