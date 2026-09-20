"""DJ contract and calibration endpoints; expensive audio work uses existing queue."""
from fastapi import Request,HTTPException
from .dj_contract import build
from .dj_review import load,save,Conflict
from .dj_plan import plan


def install(app,store):
    def contract(identifier):
        report=store.get_report(identifier)
        return build(report,load(store,report)['current'])

    @app.get('/api/analysis-lab/reports/{identifier}/dj')
    def dj_report(identifier:str):
        result=contract(identifier)
        result['review_history']=load(store,store.get_report(identifier))['history']
        return result

    @app.post('/api/analysis-lab/reports/{identifier}/dj-review')
    async def dj_review(identifier:str,request:Request):
        try:
            save(store,store.get_report(identifier),await request.json())
            return contract(identifier)
        except Conflict as exc:raise HTTPException(409,str(exc))

    @app.post('/api/analysis-lab/dj/plan')
    async def dj_plan(request:Request):
        body=await request.json()
        if not isinstance(body,dict) or not isinstance(body.get('a_report_id'),str) or not isinstance(body.get('b_report_id'),str):
            raise ValueError('请指定 A、B 的报告编号')
        a=contract(body['a_report_id']);b=contract(body['b_report_id'])
        result=plan(a,b,body.get('target_bpm'),body.get('long_intro_policy'))
        # A plan is immutable and replayable even if either track is re-analyzed later.
        root=store.root/'dj-plans';root.mkdir(exist_ok=True)
        store.write(root/(result['id']+'.json'),{'plan':result,'a':a,'b':b})
        return result
