import copy
import json
import hashlib
import pathlib
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests import test_metric_gateway as fixtures


class DeferredExecutor:
    def __init__(self):self.tasks=[]
    def submit(self,fn,*args):self.tasks.append((fn,args))


class PlanGatewayTests(unittest.TestCase):
    def setUp(self):
        from metric_mix.plan_gateway import PlanService,install_plan_routes
        from metric_mix.prepare import worker_version
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
        self.a,self.b=fixtures.CueValidationTest().tracks()
        self.execution_root=self.root/'execution'
        self.publish_execution()
        env=patch.dict(os.environ,{'HARBEAT_PLAN_CLOUD_EXECUTION_ROOT':str(self.execution_root)})
        env.start();self.addCleanup(env.stop)
        self.executor=DeferredExecutor()
        def trusted(data):
            from metric_mix.prepare import validated_plan
            if set(data)!={'from','to','windowId','start'} or data['from']!=self.a['id'] or data['to']!=self.b['id']:raise ValueError('invalid request')
            validated_plan(self.a,self.b,data['windowId'],data['start'])
            return {'a':copy.deepcopy(self.a),'b':copy.deepcopy(self.b),'windowId':data['windowId'],'start':data['start'],'codeVersion':worker_version(),'jobId':'0'*64}
        self.service=PlanService(self.root,'https://example.test',trusted,planner_sha256='1'*64,executor=self.executor)
        self.app=FastAPI();install_plan_routes(self.app,self.service);self.client=TestClient(self.app)
        self.request={'from':self.a['id'],'to':self.b['id'],'windowId':'w','start':4}
        self.headers={'Origin':'https://example.test'}

    def publish_execution(self, revision=0):
        rows=[];(self.execution_root/'profiles').mkdir(parents=True,exist_ok=True)
        for track in (self.a,self.b):
            p=track['provenance']
            stems={stem:('c' if stem=='vocals' else 'd')*64 for stem in ('drums','bass','other','vocals')}
            profile={'schema':'harbeat.execution-profile.v1','trackId':track['id'],'runId':p['runId'],
                'sourceSha256':p['masterSha256'],'reportSha256':p['reportSha256'],'manifestSha256':str(revision%10)*64,
                'revision':revision,'stems':{stem:{'sourceSha256':value} for stem,value in stems.items()}}
            raw=json.dumps(profile).encode();checksum=hashlib.sha256(raw).hexdigest()
            (self.execution_root/'profiles'/(checksum+'.json')).write_bytes(raw)
            rows.append({**{key:profile[key] for key in ('trackId','runId','sourceSha256','reportSha256','manifestSha256')},
                'profile':{'sha256':checksum},'stemSha256':stems})
        (self.execution_root/'index.json').write_text(json.dumps({'schema':'harbeat.execution-library.v1','tracks':rows}))

    def source_binding(self,track):
        index=json.loads((self.execution_root/'index.json').read_text())
        row=next(row for row in index['tracks'] if row['trackId']==track['id'])
        return {'trackId':track['id'],'runId':row['runId'],'masterSha256':row['sourceSha256'],
            'reportSha256':row['reportSha256'],'vocalSha256':row['stemSha256']['vocals'],
            'manifestSha256':row['manifestSha256'],'profileSha256':row['profile']['sha256'],'stemSha256':row['stemSha256']}

    def test_profile_republication_expires_cached_approval_and_enqueues_new_identity(self):
        response=self.client.post('/plans',json=self.request,headers=self.headers)
        identity=response.json()['id'];fn,args=self.executor.tasks.pop()
        with patch.object(self.service,'remote',return_value=self.result(args[0])):fn(*args)
        self.publish_execution(revision=1)
        self.assertEqual(self.client.get('/plans/'+identity).status_code,404)
        retry=self.client.post('/plans',json=self.request,headers=self.headers)
        self.assertEqual(retry.status_code,202,retry.text)
        self.assertNotEqual(retry.json()['id'],identity)
        self.assertEqual(len(self.executor.tasks),1)

    def test_ready_proof_must_match_exact_requested_execution_profile(self):
        response=self.client.post('/plans',json=self.request,headers=self.headers)
        identity=response.json()['id'];fn,args=self.executor.tasks.pop();wrong=self.result(args[0])
        wrong['sourceProof']['a']['profileSha256']='f'*64
        with patch.object(self.service,'remote',return_value=wrong):fn(*args)
        self.assertEqual(self.client.get('/plans/'+identity).json()['status'],'failed')

    def test_origin_size_extra_fields_and_cue_boundaries(self):
        self.assertEqual(self.client.post('/plans',json=self.request).status_code,403)
        self.assertEqual(self.client.post('/plans',content=b'x'*8193,headers=self.headers).status_code,413)
        for change in ({'start':29},{'path':'/mnt/nas/private.wav'},{'start':float('inf')}):
            body={**self.request,**change}
            response=self.client.post('/plans',content=json.dumps(body),headers=self.headers)
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.executor.tasks,[])
        self.assertEqual(self.client.get('/plans/not-a-hash').status_code,404)

    def test_queue_is_bounded_and_duplicate_requests_reuse_slot(self):
        first=self.client.post('/plans',json=self.request,headers=self.headers)
        self.assertEqual(first.status_code,202,first.text)
        again=self.client.post('/plans',json=self.request,headers=self.headers)
        self.assertEqual(again.status_code,200)
        for start in (6,8):self.assertEqual(self.client.post('/plans',json={**self.request,'start':start},headers=self.headers).status_code,202)
        self.assertEqual(self.client.post('/plans',json={**self.request,'start':10},headers=self.headers).status_code,429)
        self.assertEqual(len(self.executor.tasks),3)

    def test_remote_failure_is_private_and_releases_queue_slot(self):
        response=self.client.post('/plans',json=self.request,headers=self.headers)
        identity=response.json()['id'];fn,args=self.executor.tasks.pop()
        with patch.object(self.service,'remote',side_effect=RuntimeError('/mnt/nas/secret /home/mark/private-key')):
            fn(*args)
        result=self.client.get('/plans/'+identity)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['status'],'failed')
        self.assertNotIn('/mnt/',result.text);self.assertNotIn('/home/',result.text)
        self.assertEqual(len(self.service.active),0)
        self.assertTrue((self.root/'private'/(identity+'.txt')).is_file())

    def test_missing_pinned_engine_configuration_does_not_enqueue(self):
        self.service.planner_sha256=''
        self.assertEqual(self.client.post('/plans',json=self.request,headers=self.headers).status_code,503)
        self.assertEqual(self.executor.tasks,[])

    def result(self,job):
        from metric_mix.prepare import validated_plan
        plan=validated_plan(job['a'],job['b'],job['windowId'],job['start'])
        return {'schema':'harbeat.jetson-mix-plan.v1','id':job['jobId'],'status':'ready','producer':'jetson',
                'analysisVersion':'jetson-decision-v1','algorithmSha256':job['plannerSha256'],
                'plan':plan,'sourceProof':{side:self.source_binding(job[side]) for side in ('a','b')},
                'controls':{'duration':plan['duration']},'metrics':{},'decision':{'recommended':'original','methods':{'original':{'eligible':True}}},
                'eq':{},'restore':plan['start']+plan['restore'],'requiredStems':[],'analysisSha256':'f'*64}

    def test_valid_node_fields_are_preserved_and_cached_without_another_job(self):
        response=self.client.post('/plans',json=self.request,headers=self.headers)
        identity=response.json()['id'];fn,args=self.executor.tasks.pop();expected=self.result(args[0])
        with patch.object(self.service,'remote',return_value=expected):fn(*args)
        value=self.client.get('/plans/'+identity)
        self.assertEqual(value.status_code,200,value.text)
        self.assertEqual(value.json(),expected,'do not mutate the canonical Node output')
        reused=self.client.post('/plans',json=self.request,headers=self.headers)
        self.assertEqual(reused.json(),expected,'cached POST must return the same complete approval as GET')
        self.assertEqual(self.executor.tasks,[])
        self.assertFalse((self.root/'media').exists(),'JSON plans never create mix WAVs')

    def test_restart_terminates_orphaned_states_and_allows_same_plan_retry(self):
        from metric_mix.plan_gateway import PlanService,install_plan_routes,atomic
        for status in ('queued','running'):
            with self.subTest(status=status):
                identity=self.service.job(self.request)['jobId']
                atomic(self.service.path(identity),{'id':identity,'status':status,'message':'pending','createdAt':1})
                restarted_executor=DeferredExecutor()
                restarted=PlanService(self.root,self.service.origin,self.service.trusted_request,
                    planner_sha256=self.service.planner_sha256,executor=restarted_executor)
                app=FastAPI();install_plan_routes(app,restarted);client=TestClient(app)
                result=client.get('/plans/'+identity)
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(result.json()['status'],'failed','a lost worker cannot remain pending forever')
                retry=client.post('/plans',json=self.request,headers=self.headers)
                self.assertEqual(retry.status_code,202,retry.text)
                self.assertEqual(retry.json()['id'],identity)
                self.assertEqual(len(restarted_executor.tasks),1)
                self.assertEqual(client.get('/plans/'+identity).json()['status'],'queued','live queued work remains pending')

    def test_forged_source_geometry_version_and_private_paths_fail_closed(self):
        for mutation in ('source','geometry','version','path','fallback'):
            response=self.client.post('/plans',json=self.request,headers=self.headers)
            identity=response.json()['id'];fn,args=self.executor.tasks.pop();result=self.result(args[0])
            if mutation=='source':result['sourceProof']['a']['masterSha256']='0'*64
            if mutation=='geometry':result['plan']['start']+=.2
            if mutation=='version':result['analysisVersion']='old'
            if mutation=='path':result['metrics']['trace']='/mnt/nas/private'
            if mutation=='fallback':result['decision']['methods']['original']['eligible']=False
            with patch.object(self.service,'remote',return_value=result):fn(*args)
            value=self.client.get('/plans/'+identity)
            self.assertEqual(value.json()['status'],'failed',mutation)
            self.assertNotIn('/mnt/nas',value.text)

    def test_old_engine_and_changed_sources_cannot_reuse_ready_plan(self):
        response=self.client.post('/plans',json=self.request,headers=self.headers)
        identity=response.json()['id'];fn,args=self.executor.tasks.pop()
        with patch.object(self.service,'remote',return_value=self.result(args[0])):fn(*args)
        self.service.planner_sha256='2'*64
        self.assertEqual(self.client.get('/plans/'+identity).status_code,404)
        self.service.planner_sha256='1'*64
        self.a['title']='updated source detail'
        self.assertEqual(self.client.get('/plans/'+identity).status_code,404)


if __name__=='__main__':unittest.main()
