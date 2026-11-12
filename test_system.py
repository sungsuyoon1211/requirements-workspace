import copy
import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from pathlib import Path

spec=importlib.util.spec_from_file_location('app',Path(__file__).with_name('server.py'))
app=importlib.util.module_from_spec(spec); spec.loader.exec_module(app)

class SystemTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.server.store=app.Store(Path(self.tmp.name))
        self.server.secure_cookie=False
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.cookie=''; self.csrf=''
        self.req('/setup','POST',{'username':'admin','name':'관리자','password':'test-password-1234'})
        self.item={'title':'가입 요건','project':'테스트 프로젝트','owner':'admin','need':'고객 가입','nextAction':'고객 확인','status':'검토','priority':'Must'}
        self.item.update(story='고객은 신규 가입을 원한다',flow='입력 → 가입 → 첫 로그인',scope='일반 가입',excluded='SNS 제외',object='회원',dataFlow='고객 입력 → 회원 시스템 저장',cta='필수 동의 후 가입 실행',applicability={'interfaces':{'status':'해당없음','reason':'독립된 회원 시스템 내부 처리'},'nfr':{'status':'해당없음','reason':'별도 공통 품질 기준으로 관리'}})

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def req(self,path,method='GET',body=None,expect=200,csrf=True):
        headers={'Cookie':self.cookie}
        if body is not None:
            headers.update({'Content-Type':'application/json','X-CSRF-Token':self.csrf if csrf else ''})
        request=urllib.request.Request(self.base+'/api'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
        try: response=urllib.request.urlopen(request)
        except urllib.error.HTTPError as e: response=e
        self.assertEqual(response.status,expect,response.read().decode() if response.status!=expect else '')
        cookie=response.headers.get('Set-Cookie')
        if cookie:self.cookie=cookie.split(';')[0]
        result=json.loads(response.read())
        if 'csrf' in result:self.csrf=result['csrf']
        return result

    def test_archive_and_conflict(self):
        created=self.req('/requirements','POST',self.item,201)
        root=Path(self.tmp.name)/'archive'/created['id']/'v000001'
        self.assertTrue((root/'requirement.json').is_file());self.assertIn('가입 요건',(root/'requirement.md').read_text(encoding='utf-8'))
        changed=dict(created,title='가입 요건 수정')
        self.req('/requirements/'+created['id'],'PUT',changed)
        self.req('/requirements/'+created['id'],'PUT',changed,409)
        self.assertEqual(len(self.req('/requirements/'+created['id']+'/history')),2)
        self.assertEqual(json.loads((root/'requirement.json').read_text(encoding='utf-8'))['title'],'가입 요건')
        # Persisted data survives a fresh store object.
        self.assertEqual(app.Store(Path(self.tmp.name)).get(created['id'])['version'],2)

    def test_policy_hold(self):
        item=dict(self.item,decisions=[{'id':'D-01','question':'계속 가입?','owner':'고객','due':'2026-10-20','status':'미정'}],scenarios=[{'id':'SC-01','given':'조회 중','when':'오류','then':'가입 완료','decision':'D-01','agreement':'합의','test':'통과'}])
        self.req('/requirements','POST',item,400)
        item['scenarios'][0].update(agreement='합의보류',test='보류',then='')
        self.req('/requirements','POST',item,201)
        item['status']='확정';self.req('/requirements','POST',item,400)

    def test_roles_csrf_and_signoff(self):
        self.req('/users','POST',{'username':'member','name':'팀원','password':'member-password-123','role':'member'})
        self.req('/requirements','POST',self.item,403,csrf=False)
        self.req('/login','POST',{'username':'member','password':'member-password-123'})
        self.req('/settings',expect=403)
        self.req('/requirements','POST',dict(self.item,status='확정'),403)
        self.req('/requirements','POST',dict(self.item,owner='member'),201)
        self.req('/logout','POST',{})
        self.req('/requirements',expect=401)

    def test_signoff_and_change(self):
        item=dict(self.item,source='고객 회의록',status='확정',scenarios=[{'id':'SC-01','given':'신규 사용자','when':'가입','then':'계정 생성','agreement':'합의','test':'미실시'}],checks={n:{'status':'해당없음','evidence':'테스트 근거'} for n in app.CHECKS})
        created=self.req('/requirements','POST',item,201)
        self.assertEqual(created['signoff']['by'],'admin')
        self.req('/requirements/'+created['id'],'PUT',created,400)
        changed=dict(created,changeReason='범위 조정',changeImpact='가입 화면',changeApprover='고객 책임자',status='완료')
        self.req('/requirements/'+created['id'],'PUT',changed,400)
        changed['scenarios'][0].update(test='통과',actual='계정 한 개 생성',tester='QA',testedAt='2026-10-16',evidence='QA-1')
        updated=self.req('/requirements/'+created['id'],'PUT',changed)
        self.assertEqual(updated['version'],2)
        updated.update(status='검토')
        draft=self.req('/requirements/'+created['id'],'PUT',updated)
        self.assertTrue(draft['everSigned']);self.assertIsNone(draft['signoff'])
        draft['changeReason']='';self.req('/requirements/'+created['id'],'PUT',draft,400)

    def test_archive_outage_and_relocation(self):
        folder=Path(self.tmp.name)/'shared';folder.mkdir()
        self.req('/settings','PUT',{'archive':str(folder)})
        created=self.req('/requirements','POST',self.item,201)
        self.assertTrue((folder/created['id']/'v000001'/'requirement.json').exists())
        self.req('/settings','PUT',{'archive':str(Path(self.tmp.name)/'archive')},400)
        offline=folder.with_name('offline');folder.rename(offline)
        self.req('/requirements',expect=503)
        self.req('/requirements','POST',self.item,503)

    def test_simultaneous_edits(self):
        item=self.req('/requirements','POST',self.item,201)
        user=self.server.store.config()['users'][0]
        results=[]
        def save():
            try:results.append(self.server.store.save(item,user,item['id'])['version'])
            except app.Problem as e:results.append(e.status)
        threads=[threading.Thread(target=save) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertCountEqual(results,[2,409])

    def test_source_text_and_validation(self):
        item=dict(self.item,title='<script>alert(1)</script> 한글')
        result=self.req('/requirements','POST',item,201)
        self.assertEqual(result['title'],item['title'])
        self.req('/requirements','POST',dict(self.item,owner='missing'),400)
        self.req('/requirements','POST',dict(self.item,priority='Won’t',excluded=''),400)
        self.req('/requirements','POST',dict(self.item,due='2026-02-30'),400)
        self.req('/setup','POST',{'username':'other','name':'기타','password':'test-password-123'},403)

    def test_failed_write_is_not_published(self):
        created=self.req('/requirements','POST',self.item,201)
        with patch.object(app, 'markdown', side_effect=OSError('simulated share failure')):
            self.req('/requirements/'+created['id'],'PUT',created,503)
        current=self.req('/requirements/'+created['id'])
        self.assertEqual(current['version'],1)
        self.assertEqual(len(self.req('/requirements/'+created['id']+'/history')),1)
        self.req('/requirements/'+created['id'],'PUT',created)

    def test_nfr_confirmation_requires_six_dimensions(self):
        item=dict(self.item,source='회의록',status='확정',scenarios=[{'id':'SC-01','given':'신규 사용자','when':'가입','then':'계정 생성','agreement':'합의','test':'미실시'}],checks={n:{'status':'해당없음','evidence':'근거'} for n in app.CHECKS},nfr=[{'what':'응답 시간','target':'95% 3초'}])
        item['applicability']['nfr']={'status':'필요','reason':''}
        self.req('/requirements','POST',item,400)
        item['nfr'][0].update(who='사용자',when='피크 시간',where='브라우저',verify='부하 테스트')
        self.req('/requirements','POST',item,201)

    def test_incomplete_can_be_collected_but_not_confirmed(self):
        minimal={'title':'주문 취소 조회','project':'분류 전','owner':'admin','need':'고객 문의 감소','nextAction':'고객 확인'}
        created=self.req('/requirements','POST',minimal,201)
        self.assertFalse(created['readiness']['ready'])
        gaps=self.req('/check','POST',created)['gaps']
        self.assertTrue(any(g['target']=='flow' for g in gaps))
        self.req('/requirements/'+created['id'],'PUT',dict(created,status='확정'),400)

    def test_professional_completeness_gate(self):
        base=dict(self.item,source='회의록',status='확정',scenarios=[{'id':'SC-01','given':'신규','when':'가입','then':'계정 생성','agreement':'합의','test':'미실시'}],checks={n:{'status':'해당없음','evidence':'실제 해당 없음 사유'} for n in app.CHECKS})
        for key in ['flow','scope','story','object','dataFlow','cta']:
            with self.subTest(key=key):
                draft=copy.deepcopy(base);draft[key]=''
                self.req('/requirements','POST',draft,400)
        draft=copy.deepcopy(base);draft['checks']['상태 정의']={'status':'정의','evidence':'상태표 참조'}
        self.req('/requirements','POST',draft,400)
        draft['states']='입력 → 완료';self.req('/requirements','POST',draft,201)
        for kind in ['interfaces','nfr']:
            draft=copy.deepcopy(base);draft['applicability'][kind]={'status':'해당없음','reason':''}
            self.req('/requirements','POST',draft,400)
            draft['applicability'][kind]={'status':'필요','reason':''}
            self.req('/requirements','POST',draft,400)
        draft=copy.deepcopy(base);draft['applicability']['interfaces']={'status':'필요','reason':''};draft['interfaces']=[{'id':'IF-01'}]
        self.req('/requirements','POST',draft,400)
        draft['interfaces'][0].update(target='결제 시스템',direction='주문 → 결제',timing='승인 시',data='거래번호',failure='상태 유지',fallback='운영자 확인',owner='연동 담당')
        self.req('/requirements','POST',draft,201)

    def make_project_requirement(self):
        p=self.req('/projects','POST',{'name':'새 프로젝트','defaultOwner':'admin','commonRules':'운영팀 승인','qualityCriteria':'조회 95% 3초 이내'},201)
        r={'schemaVersion':2,'projectId':p['id'],'title':'버튼 문구 수정','need':'고객의 혼동 감소','flow':'주문 상세를 열면 취소 버튼을 표시','expected':'버튼에 취소 요청이라는 문구 표시','owner':'admin','nextAction':'내용 확인','kind':'화면·문구 수정','questions':{'exceptions':'없어요','interfaces':'없어요','policy':'없어요'}}
        return p,r

    def test_project_snapshot_and_nested_archive(self):
        p,r=self.make_project_requirement()
        r['project']='위조 이름';r['projectSnapshot']={'commonRules':'위조 기준'}
        created=self.req('/requirements','POST',r,201)
        self.assertEqual(created['project'],'새 프로젝트')
        self.assertEqual(created['projectSnapshot']['commonRules'],'운영팀 승인')
        folder=Path(self.tmp.name)/'archive'/'projects'/p['id']/created['id']
        original=(folder/'v000001'/'requirement.json').read_bytes()
        changed=self.req('/projects/'+p['id'],'PUT',dict(p,name='변경된 이름',commonRules='팀장 승인'))
        self.req('/projects/'+p['id'],'PUT',p,409)
        saved=self.req('/requirements/'+created['id'],'PUT',created)
        self.assertEqual(saved['projectSnapshot']['version'],2)
        self.assertEqual(saved['project'],'변경된 이름')
        self.assertEqual((folder/'v000001'/'requirement.json').read_bytes(),original)
        self.assertEqual(len(self.req('/requirements/'+created['id']+'/history')),2)

    def test_legacy_projects_preserve_history(self):
        old=self.req('/requirements','POST',self.item,201)
        path=Path(self.tmp.name)/'archive'/old['id']/'v000001'/'requirement.json'
        original=path.read_bytes()
        projects=self.req('/projects')
        self.assertEqual(projects[0]['name'],self.item['project'])
        fetched=self.req('/requirements/'+old['id'])
        self.assertEqual(fetched['projectId'],projects[0]['id'])
        upgrade=dict(fetched,schemaVersion=2,kind='기능 변경',expected='회원 계정 생성',questions={'exceptions':'모르겠어요','interfaces':'모르겠어요','policy':'모르겠어요'})
        self.req('/requirements/'+old['id'],'PUT',upgrade)
        self.assertEqual(path.read_bytes(),original)
        self.assertEqual(len(self.req('/requirements/'+old['id']+'/history')),2)

    def test_proportionate_confirmation_and_unknown_questions(self):
        p,r=self.make_project_requirement()
        # Cosmetic changes can be confirmed without unrelated state models or NFR rows.
        confirmed=self.req('/requirements','POST',dict(r,status='확정'),201)
        self.assertTrue(confirmed['readiness']['ready'])
        r['questions']['interfaces']='모르겠어요'
        draft=self.req('/requirements','POST',r,201)
        self.assertFalse(draft['readiness']['ready'])
        self.req('/requirements','POST',dict(r,status='확정'),400)
        r['questions']['interfaces']='있어요';r['interfaces']=[{'id':'IF-01'}]
        self.req('/requirements','POST',dict(r,status='확정'),400)
        r['questions']['interfaces']='없어요';r['interfaces']=[];r['kind']='업무·정책 변경'
        self.req('/requirements','POST',dict(r,status='확정'),400)
        r.update(scope='전체 취소',states='접수 → 승인 → 완료')
        self.req('/requirements','POST',dict(r,status='확정'),201)

    def test_v2_completion_and_project_permissions(self):
        p,r=self.make_project_requirement()
        self.req('/requirements','POST',dict(r,status='완료'),400)
        verification={'status':'통과','actual':'문구 확인','tester':'QA','date':'2026-10-19','evidence':'테스트 화면 링크'}
        self.req('/requirements','POST',dict(r,status='완료',verification=verification),201)
        self.req('/users','POST',{'username':'member','name':'담당자','password':'member-password-123','role':'member'})
        self.req('/login','POST',{'username':'member','password':'member-password-123'})
        self.req('/projects','POST',{'name':'권한 없음','defaultOwner':'member'},403)
        self.req('/requirements','POST',dict(r,owner='member'),201)
        self.req('/requirements','POST',dict(r,owner='member',status='확정'),403)

    def test_invalid_project_and_cross_project_move(self):
        p,r=self.make_project_requirement()
        self.req('/requirements','POST',dict(r,projectId='PRJ-000000000000'),400)
        saved=self.req('/requirements','POST',r,201)
        second=self.req('/projects','POST',{'name':'다른 프로젝트','defaultOwner':'admin'},201)
        self.req('/requirements/'+saved['id'],'PUT',dict(saved,projectId=second['id']),400)
        self.req('/settings','PUT',{'archive':str(Path(self.tmp.name))},400)


    def test_definition_levels_validate_and_reach_initial_and_delta_calls(self):
        p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/sessions'
        self.req(base,'POST',{'level':'INVALID'},400)
        self.req(base,'POST',{'level':[]},400)
        default=self.req(base,'POST',{},201)
        self.assertEqual(default['level'],'MIDIUN')
        full={'message':'완료 결과는 무엇인가요?','choices':[],'candidates':[],'gaps':[],
              'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        full['draft']['title']='주문 취소'
        for level in ['ROW','MIDIUN','HARD','VERYHARD']:
            with self.subTest(level=level):
                session=self.req(base,'POST',{'level':level},201)
                with patch.object(app.ai_guide,'credentials',return_value=('mock','mock')),patch.object(app.ai_guide,'call_model',return_value=full) as model:
                    saved=self.req(base+'/'+session['id'],'POST',{'version':0,'message':'주문 취소'})
                self.assertEqual(saved['level'],level)
                self.assertEqual(model.call_args.args[2]['definitionLevel'],level)
                self.assertEqual(model.call_args.args[2]['definitionCriteria'],app.ai_guide.requirement_levels.PROFILES[level])
                self.assertIn('요건 정의 레벨: '+level,model.call_args.kwargs['instructions'])
                self.req(base+'/'+session['id'],'POST',{'version':1,'message':'답','level':'bad'},400)
                with patch.object(app.ai_guide,'credentials',return_value=('mock','mock')),patch.object(app.ai_guide,'call_model',return_value=self.empty_delta()) as model:
                    changed=self.req(base+'/'+session['id'],'POST',{'version':1,'message':'쉽게 진행','level':'ROW'})
                self.assertEqual(changed['level'],'ROW')
                self.assertEqual(changed['result']['draft']['title'],'주문 취소')
                self.assertIn('요건 정의 레벨: ROW',model.call_args.kwargs['instructions'])
                self.assertEqual(next(x for x in self.req(base) if x['id']==session['id'])['level'],'ROW')

    def test_definition_levels_apply_to_installed_ai_providers(self):
        p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/sessions'
        full={'message':'질문','choices':[],'candidates':[],'gaps':[],
              'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        for provider in ['codex','claude']:
            for level in ['ROW','MIDIUN','HARD','VERYHARD']:
                with self.subTest(provider=provider,level=level):
                    app.atomic_json(self.server.store.ai_data/'ai-settings.json',{'provider':provider})
                    session=self.req(base,'POST',{'level':level},201)
                    with patch.object(app.ai_guide.local_ai,'invoke',return_value=full) as invoke:
                        saved=self.req(base+'/'+session['id'],'POST',{'version':0,'message':'시작'})
                    self.assertEqual(invoke.call_args.args[1]['definitionLevel'],level)
                    self.assertIn('요건 정의 레벨: '+level,invoke.call_args.args[2])
                    self.assertEqual(saved['level'],level)

    def test_definition_level_legacy_rollover_and_failure_preservation(self):
        p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/sessions'
        session=self.req(base,'POST',{},201)
        file=Path(self.tmp.name)/'archive/projects'/p['id']/'guide/sessions'/(session['id']+'.json')
        session.pop('level');session['messages']=[{'role':'user','text':'기존 답'}]*60
        app.atomic_json(file,session)
        full={'message':'질문','choices':[],'candidates':[],'gaps':[],
              'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        with patch.object(app.ai_guide,'credentials',return_value=('mock','mock')),patch.object(app.ai_guide,'call_model',side_effect=app.Problem('연결 실패',502)):
            self.req(base+'/'+session['id'],'POST',{'version':0,'message':'추가','level':'HARD'},502)
        self.assertEqual(json.loads(file.read_text()),session)
        with patch.object(app.ai_guide,'credentials',return_value=('mock','mock')),patch.object(app.ai_guide,'call_model',side_effect=[app.Problem('context window exceeded',502),full]) as model:
            saved=self.req(base+'/'+session['id'],'POST',{'version':0,'message':'추가'})
        self.assertEqual(saved['level'],'MIDIUN')
        self.assertNotEqual(saved['id'],session['id'])
        self.assertEqual(saved['continuedFrom'],session['id'])
        self.assertEqual(model.call_args.args[2]['definitionLevel'],'MIDIUN')

    def test_ai_sources_and_private_sessions(self):
        p,r=self.make_project_requirement(); base='/projects/'+p['id']+'/guide/'
        source=self.req(base+'sources','POST',{'name':'RFP 1장','text':'고객은 주문을 취소할 수 있다.'},201)
        session=self.req(base+'sessions','POST',{},201)
        self.assertEqual(self.req(base+'sources')[0]['id'],source['id'])
        self.req(base+'sources','POST',{'name':'bad','text':''},400)
        self.req(base+'sources','POST',{'name':'bad','text':'ok'},403,csrf=False)
        self.req('/users','POST',{'username':'guide-member','name':'팀원','password':'member-password-123','role':'member'})
        self.req('/login','POST',{'username':'guide-member','password':'member-password-123'})
        self.assertEqual(self.req(base+'sessions'),[])
        self.req(base+'sessions/'+session['id'],'POST',{'version':0,'message':'hello'},403)
        self.req('/ai/connect','POST',{'key':'not-a-real-key','model':'mock'},403)

    def test_ai_turn_and_evidence_do_not_register(self):
        p,r=self.make_project_requirement(); base='/projects/'+p['id']+'/guide/'
        source=self.req(base+'sources','POST',{'name':'회의록','text':'배송 전 주문은 취소 가능하다.'},201)
        session=self.req(base+'sessions','POST',{},201)
        result={'message':'취소 처리 후 어떤 결과를 보여줄까요?','choices':['접수 번호','모르겠어요'],'candidates':['주문 취소'],'gaps':['취소 실패 처리'], 'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[], 'evidence':[{'sourceId':source['id'],'quote':'배송 전 주문은 취소 가능하다.'},{'sourceId':source['id'],'quote':'없는 인용'}]}
        result['draft'].update(title='주문 취소',need='고객 요청')
        with patch.object(app.ai_guide,'credentials',return_value=('mock','mock-model')),patch.object(app.ai_guide,'call_model',return_value=result):
            saved=self.req(base+'sessions/'+session['id'],'POST',{'version':0,'message':'주문 취소를 정리해줘'})
        self.assertEqual(saved['version'],1);self.assertEqual(len(saved['result']['evidence']),1)
        self.assertEqual(self.req('/requirements'),[])
        self.req(base+'sessions/'+session['id'],'POST',{'version':0,'message':'중복'},409)
        self.assertEqual(self.req(base+'sessions')[0]['messages'][0]['text'],'주문 취소를 정리해줘')

    def test_ai_missing_connection_preserves_session(self):
        p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/'
        session=self.req(base+'sessions','POST',{},201)
        with patch.object(app.ai_guide,'credentials',return_value=('','')):
            self.req(base+'sessions/'+session['id'],'POST',{'version':0,'message':'시작'},503)
        self.assertEqual(self.req(base+'sessions')[0]['version'],0)
        self.assertEqual(self.req(base+'sessions')[0]['messages'],[])

    def test_ai_file_extract_and_project_isolation(self):
        import base64,io,zipfile
        p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/'
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>요건 원문</w:t></w:r></w:p></w:body></w:document>')
        saved=self.req(base+'sources','POST',{'name':'고객 RFP','fileName':'sample.docx','fileData':base64.b64encode(raw.getvalue()).decode()},201)
        self.assertEqual(saved['text'],'요건 원문');self.assertEqual(saved['name'],'고객 RFP')
        self.req(base+'sources','POST',{'name':'PDF','fileName':'x.pdf','fileData':'YWJj'},400)
        req=self.req('/requirements','POST',r,201)
        other=self.req('/projects','POST',{'name':'별도 프로젝트','defaultOwner':'admin'},201)
        self.req('/projects/'+other['id']+'/guide/sessions','POST',{'requirementId':req['id']},400)

    @unittest.skipUnless(__import__('os').name=='nt','Windows DPAPI')
    def test_ai_key_protection_roundtrip(self):
        protected=app.ai_guide.protect('unit-test-secret-only')
        self.assertNotIn('unit-test-secret-only',protected)
        self.assertEqual(app.ai_guide.protect(protected,True),'unit-test-secret-only')


    def test_local_ai_config_stays_on_pc(self):
        self.server.store.ai_data=Path(self.tmp.name)/'my-pc'
        self.server.store.ai_data.mkdir()
        result={'message':'연결됨','choices':[],'candidates':[],'gaps':[],'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        with patch.object(app.ai_guide.local_ai,'invoke',return_value=result),patch.object(app.ai_guide.local_ai,'executable',return_value='fake.exe'):
            status=self.req('/ai/local-connect','POST',{'provider':'codex'})
            self.assertTrue(status['configured']);self.assertEqual(status['provider'],'codex')
        self.assertTrue((self.server.store.ai_data/'ai-settings.json').exists())
        self.assertFalse((self.server.store.data/'ai-settings.json').exists())
        self.req('/ai/local-connect','POST',{'provider':'invalid'},400)

    def test_multiple_store_instances_keep_version_atomic(self):
        from concurrent.futures import ThreadPoolExecutor
        p,r=self.make_project_requirement()
        saved=self.req('/requirements','POST',r,201)
        other=app.Store(Path(self.tmp.name),Path(self.tmp.name)/'second-pc')
        user=self.server.store.config()['users'][0]
        def update(store):
            try: store.save(dict(saved,title='다중 PC 수정'),user,saved['id']);return 'ok'
            except app.Problem as e:return e.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(update,[self.server.store,other]))
        self.assertCountEqual(results,['ok',409])
        self.assertEqual(other.get(saved['id'])['version'],2)

    def test_os_lock_between_processes(self):
        import subprocess,sys
        folder=Path(self.tmp.name)
        counter=folder/'counter.txt';counter.write_text('0')
        code="from pathlib import Path; from shared_lock import SharedLock; import sys,time; p=Path(sys.argv[1]); lock=SharedLock(p/'counter.lock'); "
        code += "\nfor i in range(12):\n with lock:\n  n=int((p/'counter.txt').read_text());time.sleep(.002);(p/'counter.txt').write_text(str(n+1))"
        children=[subprocess.Popen([sys.executable,'-c',code,str(folder)],cwd=Path(__file__).parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        for child in children:
            out,err=child.communicate(timeout=20)
            self.assertEqual(child.returncode,0,err.decode(errors='replace'))
        self.assertEqual(counter.read_text(),'24')


    def test_selected_model_saved_and_used_for_turn(self):
        result={'message':'질문','choices':[],'candidates':[],'gaps':[],'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        with patch.object(app.ai_guide.local_ai,'invoke',return_value=result) as invoke,patch.object(app.ai_guide.local_ai,'executable',return_value='fake.exe'):
            selected=self.req('/ai/local-connect','POST',{'provider':'claude','model':'sonnet'})
            self.assertEqual(selected['model'],'sonnet');self.assertEqual(invoke.call_args.kwargs['model'],'sonnet')
            p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/sessions'
            session=self.req(base,'POST',{},201)
            self.req(base+'/'+session['id'],'POST',{'message':'작성 시작','version':0})
            self.assertEqual(invoke.call_args.kwargs['model'],'sonnet')
        self.req('/ai/local-connect','POST',{'provider':'codex','model':'--dangerously-bypass-approvals-and-sandbox'},400)

    def test_account_and_login_routes_keep_workspace_identity(self):
        with patch.object(app.ai_guide.local_ai,'account_info',return_value={'loggedIn':True,'account':'example@example.com','models':[]}) as info:
            self.assertTrue(self.req('/ai/account/codex')['loggedIn'])
            self.assertEqual(info.call_args.args[0],'codex')
        with patch.object(app.ai_guide.local_ai,'start_login',return_value={'state':'running'}) as start:
            self.req('/ai/login','POST',{'provider':'claude'})
            self.assertEqual(start.call_args.args[0],'claude')
            self.req('/ai/login','POST',{'provider':'claude'},403,csrf=False)
            self.req('/ai/login','POST',{'provider':'bad'},400)
        self.assertEqual(self.req('/me')['user']['username'],'admin')

    def test_model_is_passed_as_cli_argument(self):
        import local_ai
        from types import SimpleNamespace
        with patch.object(local_ai,'executable',return_value='claude.exe'),patch.object(local_ai.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"structured_output":{"ok":true}}')) as run:
            local_ai.invoke('claude',{},'test',{},app.Problem,model='sonnet')
            args=run.call_args.args[0]
            self.assertEqual(args[-2:],['--model','sonnet'])
            self.assertNotIn('shell',run.call_args.kwargs)


    def test_more_than_thirty_open_questions_survive_save(self):
        p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/sessions'
        session=self.req(base,'POST',{},201)
        result={'message':'다음 질문입니다.','choices':[],'candidates':[],'gaps':['확인 질문 '+str(i) for i in range(35)],'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        app.atomic_json(self.server.store.ai_data/'ai-settings.json',{'provider':'claude','model':'opus'})
        with patch.object(app.ai_guide.local_ai,'invoke',return_value=result):
            saved=self.req(base+'/'+session['id'],'POST',{'message':'답변','version':0})
        self.assertEqual(saved['version'],1)
        self.assertEqual(len(saved['result']['gaps']),35)
        self.assertEqual(saved['messages'][0]['text'],'답변')
        self.assertEqual(len(self.req(base)[0]['result']['gaps']),35)

    def test_unlimited_content_roundtrips_without_count_based_rollover(self):
        p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/'
        # Cross the former file, HTTP request, source text/count/total ceilings.
        import base64
        text='자료'*210000
        source=self.req(base+'sources','POST',{'name':'큰 자료','fileName':'large.txt','fileData':base64.b64encode(text.encode()).decode()},201)
        self.assertEqual(source['text'],text)
        for i in range(21): self.req(base+'sources','POST',{'name':str(i),'text':'추가'},201)
        self.assertEqual(len(self.req(base+'sources')),22)
        r.update(status='수집',decisions=[{'id':f'D-{i}','question':f'질문 {i}','status':'미정','owner':'','due':''} for i in range(250)],expected='긴'*250000)
        saved=self.req('/requirements','POST',r,201)
        self.assertEqual(len(self.req('/requirements/'+saved['id'])['decisions']),250)
        session=self.req(base+'sessions','POST',{},201)
        session['messages']=[{'role':'user','text':str(i)} for i in range(1000)]
        file=Path(self.tmp.name)/'archive/projects'/p['id']/'guide/sessions'/(session['id']+'.json');app.atomic_json(file,session)
        result={'message':'질문','choices':[],'candidates':[],'gaps':[f'질문 {i}' for i in range(250)],'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        with patch.object(app.ai_guide,'credentials',return_value=('mock','mock')),patch.object(app.ai_guide,'call_model',return_value=result) as model:
            continued=self.req(base+'sessions/'+session['id'],'POST',{'version':0,'message':'답'*7000})
        self.assertEqual(continued['id'],session['id'])
        self.assertEqual(len(continued['messages']),1002)
        self.assertEqual(next(x['text'] for x in self.req(base+'sources') if x['id']==source['id']),text)
        self.assertEqual(model.call_args.args[2]['contextCoverage']['mode'],'retrieval')
        self.assertEqual(len(model.call_args.args[2]['conversation']),8)
        self.assertEqual(len(continued['result']['gaps']),250)

    def test_ai_schema_limits_match_validator(self):
        schema=app.ai_guide.schema()
        result={'message':'안내','choices':[],'candidates':[],'gaps':['질문']*100,'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        self.assertNotIn('maxItems',schema['properties']['gaps'])
        self.assertTrue(app.ai_guide.valid_output(result,schema))
        result['gaps'].append('추가 질문')
        self.assertTrue(app.ai_guide.valid_output(result,schema))
        app.ai_guide.ensure_output(result,app.Problem)
        result['gaps']=[];result['draft']['need']=None
        self.assertFalse(app.ai_guide.valid_output(result,schema))
        self.assertIn('need',app.ai_guide.output_issues(result,schema)[0])

    def test_ai_questions_can_be_saved_before_assignment_but_not_finalized(self):
        response=urllib.request.urlopen(self.base+'/guide-polish.css')
        self.assertIn('text/css',response.headers['Content-Type'])
        self.assertIn(b'.guide-refined',response.read())
        p,r=self.make_project_requirement()
        r.update(status='수집',decisions=[{'id':'D-01','question':'배송 후 취소를 허용할까요?','status':'미정','owner':'','due':''}])
        saved=self.req('/requirements','POST',r,201)
        self.assertEqual(saved['decisions'][0]['question'],r['decisions'][0]['question'])
        self.assertFalse(saved['readiness']['ready'])
        self.req('/requirements/'+saved['id'],'PUT',dict(saved,status='확정'),400)
        decided=copy.deepcopy(saved)
        decided['decisions'][0].update(status='결정',answer='허용',evidence='회의록')
        self.req('/requirements/'+saved['id'],'PUT',decided,400)

    def test_connection_archive_references_and_version_baseline(self):
        p,r=self.make_project_requirement()
        first=self.req('/requirements','POST',dict(r,title='회원가입'),201)
        relation={'requirementId':first['id'],'type':'선행 필요','reason':'회원이 필요','status':'확인'}
        second=self.req('/requirements','POST',dict(r,title='로그인',relations=[relation],dataUses=[{'name':' 회원  정보 ','operation':'조회','description':'식별자 조회','status':'확인'}]),201)
        self.assertEqual(second['relations'][0]['targetVersion'],1)
        self.assertEqual(second['dataUses'][0]['name'],'회원 정보')
        self.assertIn('데이터 사용 관계',app.markdown(second))
        self.assertIn(first['id'],app.markdown(second))
        first2=self.req('/requirements/'+first['id'],'PUT',dict(first,title='회원가입 변경'))
        saved=self.req('/requirements/'+second['id'],'PUT',dict(second,need='변경해도 연결 버전 유지'))
        self.assertEqual(saved['relations'][0]['targetVersion'],1)
        self.req('/requirements/'+first['id'],'PUT',dict(first2,relations=[dict(relation,requirementId=second['id'])]),400)
        self.req('/requirements/'+first['id'],'PUT',dict(first2,relations=[relation]),400)
        self.req('/requirements','POST',dict(r,relations=[dict(relation,requirementId='REQ-000000000000')]),400)
        other=self.req('/projects','POST',{'name':'다른 프로젝트','defaultOwner':'admin'},201)
        self.req('/requirements','POST',dict(r,projectId=other['id'],relations=[relation]),400)

    def test_connection_proposals_require_review_and_invalid_data_rejected(self):
        p,r=self.make_project_requirement()
        row={'name':'회원','operation':'생성','description':'계정 생성','status':'제안'}
        saved=self.req('/requirements','POST',dict(r,dataUses=[row]),201)
        self.assertFalse(saved['readiness']['ready'])
        self.req('/requirements/'+saved['id'],'PUT',dict(saved,status='확정'),400)
        self.req('/requirements','POST',dict(r,dataUses=[row,row]),400)
        self.req('/requirements','POST',dict(r,dataUses=[dict(row,operation='실행')]),400)
        confirmed=self.req('/requirements/'+saved['id'],'PUT',dict(saved,dataUses=[dict(row,status='확인')]))
        self.assertTrue(confirmed['readiness']['ready'])

    def test_long_chat_continues_without_losing_draft_or_last_answer(self):
        p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/'
        session=self.req(base+'sessions','POST',{},201)
        result={'message':'다음 질문','choices':[],'candidates':[],'gaps':['미정 정책'],'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        result['draft'].update(title='회원가입',need='가입 필요')
        session.update(version=30,result=result,messages=[{'role':'user' if i%2==0 else 'assistant','text':str(i)} for i in range(60)])
        file=Path(self.tmp.name)/'archive/projects'/p['id']/'guide/sessions'/(session['id']+'.json')
        app.atomic_json(file,session)
        delta=self.empty_delta()
        with patch.object(app.ai_guide,'credentials',return_value=('mock','mock')),patch.object(app.ai_guide,'call_model',side_effect=[app.Problem('context window exceeded',502),delta]) as model:
            saved=self.req(base+'sessions/'+session['id'],'POST',{'version':30,'message':'외국인도 휴대폰 인증부터'})
        context=model.call_args.args[2]
        self.assertEqual(len(context['conversation']),8)
        self.assertEqual(context['contextCoverage']['mode'],'retrieval')
        self.assertEqual(context['previousDraft']['gaps'],['미정 정책'])
        self.assertEqual(context['conversation'][-1]['text'],'외국인도 휴대폰 인증부터')
        self.assertNotEqual(saved['id'],session['id'])
        self.assertEqual(saved['continuedFrom'],session['id'])
        self.assertEqual(saved['rootSessionId'],session['id'])
        self.assertEqual(saved['messages'][0]['text'],'외국인도 휴대폰 인증부터')
        old=json.loads(file.read_text(encoding='utf-8'))
        self.assertEqual(old['messages'],session['messages'])
        self.assertEqual(old['result'],session['result'])
        self.assertEqual(old['continuedTo'],saved['id'])
        self.req(base+'sessions/'+session['id'],'POST',{'version':31,'message':'중복'},409)
        self.assertEqual(len(self.req(base+'sessions')),2)

    def test_context_retry_once_and_failure_does_not_create_session(self):
        p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/'
        session=self.req(base+'sessions','POST',{},201)
        session.update(version=1,messages=[{'role':'user','text':'초기 요청'},{'role':'assistant','text':'질문'}])
        file=Path(self.tmp.name)/'archive/projects'/p['id']/'guide/sessions'/(session['id']+'.json');app.atomic_json(file,session)
        with patch.object(app.ai_guide,'credentials',return_value=('mock','mock')),patch.object(app.ai_guide,'call_model',side_effect=app.Problem('context window exceeded',502)) as model:
            self.req(base+'sessions/'+session['id'],'POST',{'version':1,'message':'마지막 답변'},502)
        self.assertEqual(model.call_count,2)
        self.assertEqual(len(self.req(base+'sessions')),1)
        self.assertEqual(json.loads(file.read_text(encoding='utf-8')),session)
        with patch.object(app.ai_guide,'credentials',return_value=('mock','mock')),patch.object(app.ai_guide,'call_model',side_effect=app.Problem('로그인 필요',503)) as model:
            self.req(base+'sessions/'+session['id'],'POST',{'version':1,'message':'답변'},503)
        self.assertEqual(model.call_count,1)

    def empty_delta(self):
        return {'message':'답변을 반영했어요. 다음 질문입니다.','choices':['선택 1','미정'],'draftChanges':[],'draftEdits':[],
                **{key:{'remove':[],'upsert':[]} for key in app.ai_guide.DELTA_LISTS}}

    def test_incremental_merge_preserves_unmodified_content(self):
        previous={'message':'이전 질문','choices':[],'candidates':[],'gaps':['해결한 질문','남은 질문'],'draft':{k:'기존 '+k for k in app.ai_guide.FIELDS},
                  'bdd':[{'given':'조건','when':'행동','then':'결과'}]*23,'evidence':[],
                  'relations':[],'dataUses':[],'interfaces':[{'target':'회원 API','direction':'조회','timing':'가입','data':'ID','failure':'유지','fallback':'확인','owner':'담당'}]}
        before=copy.deepcopy(previous);delta=self.empty_delta()
        delta['draftEdits']=[{'field':'policyDetail','before':'기존 policyDetail','after':'공통 약관에 동의한다.'}]
        delta['gaps']={'remove':[0],'upsert':[{'index':-1,'value':'새 확인 질문'}]}
        merged=app.ai_guide.apply_delta(previous,delta,app.Problem)
        self.assertEqual(previous,before)
        self.assertEqual(merged['bdd'],previous['bdd']);self.assertEqual(merged['interfaces'],previous['interfaces'])
        self.assertEqual(merged['draft']['flow'],previous['draft']['flow'])
        self.assertEqual(merged['draft']['policyDetail'],'공통 약관에 동의한다.')
        self.assertEqual(merged['gaps'],['남은 질문','새 확인 질문'])
        for invalid in [dict(delta,gaps={'remove':[100],'upsert':[]}),dict(delta,gaps={'remove':[0],'upsert':[{'index':0,'value':'중복'}]}),
                        dict(delta,draftChanges=[{'field':'unknown','value':'값'}]),dict(delta,gaps={'remove':[True],'upsert':[]})]:
            with self.assertRaises(app.Problem):app.ai_guide.apply_delta(previous,invalid,app.Problem)
        self.assertEqual(previous,before)

    def test_incremental_turn_uses_patch_contract_and_persists_full_snapshot(self):
        p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/'
        session=self.req(base+'sessions','POST',{},201)
        previous={'message':'질문','choices':[],'candidates':[],'gaps':['약관 확인'],'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        previous['draft'].update(title='회원가입',need='가입 필요',flow='기존 가입 흐름')
        session.update(version=1,result=previous,messages=[{'role':'user','text':'가입 요청'},{'role':'assistant','text':'약관은?'}])
        file=Path(self.tmp.name)/'archive/projects'/p['id']/'guide/sessions'/(session['id']+'.json');app.atomic_json(file,session)
        app.atomic_json(self.server.store.ai_data/'ai-settings.json',{'provider':'claude','model':'opus'})
        delta=self.empty_delta();delta['draftChanges']=[{'field':'policyDetail','value':'공통 약관 동의'}];delta['gaps']['remove']=[0]
        with patch.object(app.ai_guide.local_ai,'invoke',return_value=delta) as invoke:
            saved=self.req(base+'sessions/'+session['id'],'POST',{'version':1,'message':'공통 약관에 동의'})
        self.assertIn('draftChanges',invoke.call_args.args[3]['properties'])
        self.assertNotIn('draft',invoke.call_args.args[3]['properties'])
        self.assertEqual(saved['result']['draft']['flow'],'기존 가입 흐름')
        self.assertEqual(saved['result']['draft']['policyDetail'],'공통 약관 동의')
        self.assertEqual(saved['result']['gaps'],[])
        metric=json.loads((self.server.store.ai_data/'performance.json').read_text(encoding='utf-8'))[-1]
        self.assertEqual(metric['mode'],'delta');self.assertEqual(metric['outcome'],'success')
        self.assertNotIn('공통 약관',json.dumps(metric,ensure_ascii=False))
        invalid=self.empty_delta();invalid['gaps']['remove']=[999]
        with patch.object(app.ai_guide.local_ai,'invoke',return_value=invalid):
            self.req(base+'sessions/'+session['id'],'POST',{'version':2,'message':'추가 답변'},502)
        self.assertEqual(json.loads(file.read_text(encoding='utf-8')),saved)

    def test_sentence_edits_preserve_other_agreements_and_reject_ambiguity(self):
        previous={'message':'질문','choices':[],'candidates':[],'gaps':[],'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        previous['draft']['flow']='본인 인증은 필수다. 가입 시 약관은 미정이다. 오류 시 입력을 유지한다. 기존 계정은 중복 생성하지 않는다.'
        patch=self.empty_delta();patch['draftEdits']=[{'field':'flow','before':'가입 시 약관은 미정이다.','after':'가입 시 공통 약관에 동의한다.'},
                                                    {'field':'flow','before':'기존 계정은 중복 생성하지 않는다.','after':'기존 계정은 중복 생성하지 않고 로그인으로 안내한다.'}]
        merged=app.ai_guide.apply_delta(previous,patch,app.Problem)
        self.assertEqual(merged['draft']['flow'],'본인 인증은 필수다. 가입 시 공통 약관에 동의한다. 오류 시 입력을 유지한다. 기존 계정은 중복 생성하지 않고 로그인으로 안내한다.')
        for edits in [[{'field':'flow','before':'없는 문장','after':'바꿈'}],patch['draftEdits']*2,[{'field':'flow','before':'','after':'추가'}]]:
            invalid=self.empty_delta();invalid['draftEdits']=edits
            with self.assertRaises(app.Problem):app.ai_guide.apply_delta(previous,invalid,app.Problem)
        invalid=self.empty_delta();invalid['draftChanges']=[{'field':'flow','value':'기존 내용 삭제'}]
        with self.assertRaises(app.Problem):app.ai_guide.apply_delta(previous,invalid,app.Problem)
        previous['draft']['flow']='반복 문장. 반복 문장.'
        invalid=self.empty_delta();invalid['draftEdits']=[{'field':'flow','before':'반복 문장.','after':'변경'}]
        with self.assertRaises(app.Problem):app.ai_guide.apply_delta(previous,invalid,app.Problem)

    def test_existing_requirement_policies_and_bdd_remain_in_ai_context(self):
        p,r=self.make_project_requirement()
        saved=self.req('/requirements','POST',dict(r,policyDetail='기존 요건의 정책 맥락',exceptionDetail='실패 시 상태 유지'),201)
        base='/projects/'+p['id']+'/guide/sessions';session=self.req(base,'POST',{},201)
        result={'message':'질문','choices':[],'candidates':[],'gaps':[],'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        with patch.object(app.ai_guide,'credentials',return_value=('mock','mock')),patch.object(app.ai_guide,'call_model',return_value=result) as model:
            self.req(base+'/'+session['id'],'POST',{'version':0,'message':'연관 요건 검토'})
        related=model.call_args.args[2]['existingRequirements'][0]
        self.assertEqual(related['policyDetail'],'기존 요건의 정책 맥락')
        self.assertEqual(related['exceptionDetail'],'실패 시 상태 유지')
        self.assertEqual(related['scenarios'],saved['scenarios'])
        self.assertEqual(related['projectSnapshot'],saved['projectSnapshot'])

    def test_bdd_accumulates_beyond_thirty_and_saves_to_requirement(self):
        p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/sessions'
        session=self.req(base,'POST',{},201)
        previous={'message':'질문','choices':[],'candidates':[],'gaps':[],'draft':{k:'' for k in app.ai_guide.FIELDS},
                  'bdd':[{'given':f'조건 {i}','when':'행동','then':'결과'} for i in range(30)],'evidence':[]}
        session.update(version=1,result=previous)
        file=Path(self.tmp.name)/'archive/projects'/p['id']/'guide/sessions'/(session['id']+'.json');app.atomic_json(file,session)
        delta=self.empty_delta();delta['bdd']['upsert']=[{'index':-1,'value':{'given':'인증 완료','when':'가입','then':'완료'}}]
        with patch.object(app.ai_guide,'credentials',return_value=('mock','mock')),patch.object(app.ai_guide,'call_model',return_value=delta) as model:
            saved=self.req(base+'/'+session['id'],'POST',{'version':1,'message':'인증 메일 없이 가입'})
        self.assertEqual(saved['result']['bdd'][:30],previous['bdd'])
        self.assertEqual(len(saved['result']['bdd']),31)
        self.assertEqual(model.call_args.args[2]['collectionLimits']['bdd'],{'current':30,'max':None})
        scenarios=[dict(x,id=f'SC-{i+1:02}',agreement='제안',test='미실시') for i,x in enumerate(saved['result']['bdd'])]
        req=self.req('/requirements','POST',dict(r,scenarios=scenarios),201)
        self.assertEqual(len(req['scenarios']),31)
        for key in ['relations','dataUses','interfaces']:
            self.assertNotIn('maxItems',app.ai_guide.schema()['properties'][key])
        hundred=copy.deepcopy(saved['result']);hundred['bdd']=[previous['bdd'][0]]*100
        self.assertTrue(app.ai_guide.valid_output(hundred,app.ai_guide.schema()))
        before=copy.deepcopy(hundred)
        self.assertEqual(len(app.ai_guide.apply_delta(hundred,delta,app.Problem)['bdd']),101)
        self.assertEqual(hundred,before)

    def test_long_draft_delta_and_requirement_save(self):
        p,r=self.make_project_requirement();base='/projects/'+p['id']+'/guide/sessions'
        session=self.req(base,'POST',{},201)
        previous={'message':'질문','choices':[],'candidates':[],'gaps':[],'draft':{k:'' for k in app.ai_guide.FIELDS},'bdd':[],'evidence':[]}
        original='기'*100000+'마지막 문장.'
        previous['draft']['expected']=original
        session.update(version=1,result=previous)
        file=Path(self.tmp.name)/'archive/projects'/p['id']/'guide/sessions'/(session['id']+'.json');app.atomic_json(file,session)
        delta=self.empty_delta();delta['draftEdits']=[{'field':'expected','before':'마지막 문장.','after':'마지막 문장. 브라우저 기본 확인 창을 표시한다.'*8}]
        with patch.object(app.ai_guide,'credentials',return_value=('mock','mock')),patch.object(app.ai_guide,'call_model',return_value=delta) as model:
            saved=self.req(base+'/'+session['id'],'POST',{'version':1,'message':'기본 확인 창 표시'})
        expected=original[:-7]+delta['draftEdits'][0]['after']
        self.assertEqual(saved['result']['draft']['expected'],expected)
        self.assertGreater(len(expected),100000)
        self.assertIsNone(model.call_args.args[2]['draftTextLimits']['expected']['max'])
        created=self.req('/requirements','POST',dict(r,expected=expected,flow='흐'*200000),201)
        self.assertEqual(created['expected'],expected)
        self.assertEqual(self.req('/requirements/'+created['id'])['flow'],'흐'*200000)
        updated=self.req('/requirements/'+created['id'],'PUT',dict(created,expected='가'*200000))
        self.assertEqual(updated['expected'],'가'*200000)
        too_long=copy.deepcopy(saved['result']);too_long['draft']['expected']='가'*200001
        app.ai_guide.ensure_output(too_long,app.Problem)
        self.req('/requirements','POST',dict(r,expected='가'*200001),201)

    def test_project_markdown_zip(self):
        p,r=self.make_project_requirement();url='/projects/'+p['id']+'/export'
        self.req(url,expect=404)
        first=self.req('/requirements','POST',dict(r,title='회원/가입: 확인'),201)
        latest=self.req('/requirements/'+first['id'],'PUT',dict(first,expected='최신 완료 기준'))
        second=self.req('/requirements','POST',dict(r,title='회원/가입: 확인'),201)
        other=self.req('/projects','POST',{'name':'다른 프로젝트','defaultOwner':'admin'},201)
        self.req('/requirements','POST',dict(r,projectId=other['id']),201)
        request=urllib.request.Request(self.base+'/api'+url,headers={'Cookie':self.cookie})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.headers.get_content_type(),'application/zip')
            with app.zipfile.ZipFile(app.io.BytesIO(response.read())) as archive:
                self.assertEqual(len(archive.namelist()),2)
                for item in [latest,second]:
                    name=next(n for n in archive.namelist() if n.startswith(item['id']))
                    self.assertNotIn('/',name);self.assertNotIn(':',name)
                    self.assertEqual(archive.read(name).decode('utf-8'),app.markdown(item))
        self.cookie='';self.req(url,expect=401)

    def test_unlimited_bdd_registration_update_and_export(self):
        p,r=self.make_project_requirement()
        result={'message':'질문','choices':[],'candidates':[],'gaps':[],'draft':{k:'' for k in app.ai_guide.FIELDS},
                'bdd':[{'given':f'조건 {i}','when':'실행','then':f'결과 {i}'} for i in range(1001)],'evidence':[]}
        self.assertNotIn('maxItems',app.ai_guide.schema()['properties']['bdd'])
        self.assertNotIn('maxItems',app.ai_guide.delta_schema()['properties']['bdd']['properties']['upsert'])
        self.assertTrue(app.ai_guide.valid_output(result,app.ai_guide.schema()))
        app.ai_guide.ensure_output(result,app.Problem)
        delta=self.empty_delta();delta['bdd']['upsert']=[{'index':-1,'value':x} for x in result['bdd'][:101]]
        merged=app.ai_guide.apply_delta(result,delta,app.Problem)
        self.assertEqual(len(merged['bdd']),1102)
        rows=[dict(x,id=f'SC-{i}',agreement='제안',test='미실시') for i,x in enumerate(merged['bdd'])]
        saved=self.req('/requirements','POST',dict(r,scenarios=rows),201)
        updated=self.req('/requirements/'+saved['id'],'PUT',dict(saved,need='수정 이유'))
        actual=self.req('/requirements/'+saved['id'])['scenarios']
        self.assertEqual(actual,saved['scenarios'])
        self.assertEqual([{k:row[k] for k in rows[0]} for row in actual],rows)
        self.assertIn('SC-1101',app.markdown(updated))

if __name__=='__main__':unittest.main(verbosity=2)

