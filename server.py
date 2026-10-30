"""Requirement workspace. Python 3.11+, standard library only."""
import argparse
import hashlib
import hmac
import json
import io
import zipfile
import os
import re
import secrets
import shutil
import threading
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import project_model
import ai_guide
from shared_lock import SharedLock

ROOT = Path(__file__).resolve().parent
LOCK = threading.RLock()
SESSIONS = {}
ATTEMPTS = {}
STATUSES = ['수집', '검토', '확정', '진행', '완료', '보류']
PRIORITIES = ['Must', 'Should', 'Could', "Won’t"]
CHECKS = ['승인·결재', '상태 정의', '예외 처리', '권한', '책임 주체', '취소·반려·재처리']

class Problem(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

def atomic_json(path, value):
    tmp = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        with tmp.open('x', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return salt + ':' + digest

def user_public(user):
    return {k: user[k] for k in ['username', 'name', 'role']}

def text(value, limit=12000):
    if not isinstance(value, str) or len(value) > limit:
        raise Problem('입력 형식 또는 글자 수를 확인해 주세요.')
    return value.strip()

def date(value):
    value = text(value, 10)
    if value:
        try:
            datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            raise Problem('날짜는 YYYY-MM-DD 형식이어야 합니다.')
    return value

def validate(payload, users):
    fields = ['title', 'project', 'owner', 'need', 'story', 'nextAction', 'source',
              'flow', 'cta', 'scope', 'excluded', 'object', 'states', 'dataFlow',
              'responsibility', 'approvalFlow', 'exceptions', 'migration', 'risk',
              'changeReason', 'changeImpact', 'changeApprover', 'design', 'successMetric']
    item = {key: text(payload.get(key, ''),project_model.NARRATIVE_LIMIT if key in project_model.NARRATIVE_FIELDS else 12000) for key in fields}
    for key, label in [('title', '요건 제목'), ('project', '프로젝트'), ('owner', '담당자'),
                       ('need', '필요한 이유'), ('nextAction', '다음 할 일')]:
        if not item[key]:
            raise Problem(label + '을(를) 입력해 주세요.')
    if item['owner'] not in [u['username'] for u in users]:
        raise Problem('등록된 담당자를 선택해 주세요.')
    item['due'] = date(payload.get('due', ''))
    item['status'] = payload.get('status', '수집')
    item['priority'] = payload.get('priority', 'Should')
    if item['status'] not in STATUSES or item['priority'] not in PRIORITIES:
        raise Problem('상태 또는 우선순위를 확인해 주세요.')
    if item['priority'] == 'Won’t' and not item['excluded']:
        raise Problem('이번 단계 제외 사유를 입력해 주세요.')
    schemas = {
        'decisions': ['id', 'question', 'owner', 'due', 'status', 'answer', 'evidence'],
        'scenarios': ['id', 'rule', 'given', 'when', 'then', 'decision', 'agreement', 'test', 'actual', 'tester', 'testedAt', 'evidence'],
        'interfaces': ['id', 'target', 'direction', 'timing', 'data', 'failure', 'fallback', 'owner'],
        'nfr': ['what', 'who', 'when', 'where', 'target', 'verify'],
    }
    for key, keys in schemas.items():
        rows = payload.get(key, [])
        if not isinstance(rows, list) or (key != 'scenarios' and len(rows) > 100):
            raise Problem('상세 항목은 목록이어야 하며 BDD 외 항목은 종류별 최대 100개입니다.')
        item[key] = []
        for row in rows:
            if not isinstance(row, dict):
                raise Problem('상세 항목의 형식을 확인해 주세요.')
            item[key].append({k: text(row.get(k, '')) for k in keys})
        if 'id' in keys:
            ids = [r['id'] for r in item[key]]
            if any(not i for i in ids) or len(ids) != len(set(ids)):
                raise Problem('상세 항목 ID는 비어 있거나 중복될 수 없습니다.')
    for d in item['decisions']:
        date(d['due'])
        if not d['question'] or d['status'] not in ['미정', '결정']:
            raise Problem('결정사항의 질문과 상태를 확인해 주세요.')
        draft_question = payload.get('schemaVersion') == 2 and item['status'] in ['수집', '검토'] and d['status'] == '미정'
        if (not d['owner'] or not d['due']) and not draft_question:
            raise Problem('결정사항에는 결정 담당자와 기한이 필요합니다.')
        if d['status'] == '결정' and not (d['answer'] and d['evidence']):
            raise Problem('결정한 사항에는 답변과 근거가 필요합니다.')
    decisions = {d['id']: d for d in item['decisions']}
    for s in item['scenarios']:
        if s['agreement'] not in ['제안', '합의', '합의보류'] or s['test'] not in ['미실시', '통과', '실패', '보류']:
            raise Problem('BDD 합의·검수 상태를 확인해 주세요.')
        if not s['given'] or not s['when']:
            raise Problem('BDD 상황과 행동을 입력해 주세요.')
        if s['decision'] and s['decision'] not in decisions:
            raise Problem('BDD에 연결한 결정 ID가 존재하지 않습니다.')
        pending = s['decision'] and decisions[s['decision']]['status'] == '미정'
        if pending and (s['agreement'] != '합의보류' or s['test'] != '보류'):
            raise Problem('정책 미정 시나리오는 합의보류·검수 보류로 저장해 주세요.')
        if not pending and not s['then']:
            raise Problem('BDD 기대 결과를 입력해 주세요.')
        if s['test'] in ['통과', '실패']:
            if s['agreement'] != '합의' or not all(s[k] for k in ['actual', 'tester', 'testedAt', 'evidence']):
                raise Problem('검수 결과에는 합의된 시나리오와 실제 결과·검수자·날짜·증빙이 필요합니다.')
        date(s['testedAt'])
    raw_checks = payload.get('checks', {})
    if not isinstance(raw_checks, dict):
        raise Problem('누락 점검의 형식을 확인해 주세요.')
    item['checks'] = {}
    for name in CHECKS:
        entry = raw_checks.get(name, {})
        if not isinstance(entry, dict):
            raise Problem('누락 점검의 형식을 확인해 주세요.')
        state = entry.get('status', '미정')
        if state not in ['미정', '정의', '해당없음']:
            raise Problem('누락 점검 상태를 확인해 주세요.')
        evidence = text(entry.get('evidence', ''))
        if state != '미정' and not evidence:
            raise Problem('정의·해당없음 항목은 근거를 작성해 주세요.')
        item['checks'][name] = {'status': state, 'evidence': evidence}
    applicability = payload.get('applicability', {})
    if not isinstance(applicability, dict):
        raise Problem('적용 여부 형식을 확인해 주세요.')
    item['applicability'] = {}
    for key in ['interfaces', 'nfr']:
        entry = applicability.get(key, {})
        if not isinstance(entry, dict) or entry.get('status', '미정') not in ['미정', '필요', '해당없음']:
            raise Problem('연동·품질 기준의 적용 여부를 확인해 주세요.')
        item['applicability'][key] = {'status': entry.get('status', '미정'), 'reason': text(entry.get('reason', ''))}
    item['policy'] = '정책 미정' if any(d['status'] == '미정' for d in item['decisions']) else '질의 없음'
    if payload.get('schemaVersion')==2:
        project_model.normalize(payload,item,Problem)
        item['projectId']=payload['projectId']
        item['projectSnapshot']=payload['projectSnapshot']
    return item

def readiness(item):
    if item.get('schemaVersion')==2:
        return project_model.readiness(item)
    gaps = []
    def add(label, target): gaps.append({'label':label, 'target':target})
    for key,label in [('story','누가 어떤 상황에서 사용할지'),('flow','처음부터 다음 업무까지의 흐름'),
                      ('scope','이번에 만들 범위'),('excluded','제외 범위 또는 제외 없음'),
                      ('object','관리할 업무 대상'),('dataFlow','데이터 생성·수정·사용 흐름'),
                      ('cta','주요 행동과 실행 조건'),('source','요청의 출처')]:
        if not str(item.get(key,'')).strip(): add(label+' 작성이 필요해요.',key)
    if not str(item.get('project','')).strip() or item.get('project')=='분류 전':
        add('프로젝트를 정해 주세요.','project')
    check_fields={'승인·결재':'approvalFlow','상태 정의':'states','예외 처리':'exceptions','권한':'responsibility','책임 주체':'responsibility','취소·반려·재처리':'exceptions'}
    for name,key in check_fields.items():
        entry=item.get('checks',{}).get(name,{})
        if entry.get('status') not in ['정의','해당없음'] or not str(entry.get('evidence','')).strip():
            add(name+' 점검과 근거를 작성해 주세요.','checks')
        elif entry['status']=='정의' and not str(item.get(key,'')).strip():
            add(name+'의 구체적인 내용을 작성해 주세요.',key)
    for key,label in [('interfaces','시스템 연결'),('nfr','품질 기준')]:
        entry=item.get('applicability',{}).get(key,{})
        rows=item.get(key,[])
        if entry.get('status')=='해당없음':
            if not str(entry.get('reason','')).strip(): add(label+'이 필요 없는 이유를 적어 주세요.','apply_'+key)
            if rows: add(label+' 항목이 있습니다. 적용 여부를 필요로 바꾸거나 항목을 정리해 주세요.','apply_'+key)
        elif entry.get('status')=='필요':
            if not rows: add(label+'을 최소 한 개 작성해 주세요.',key)
            required=['id','target','direction','timing','data','failure','fallback','owner'] if key=='interfaces' else ['what','who','when','where','target','verify']
            if any(any(not str(row.get(k,'')).strip() for k in required) for row in rows): add(label+'의 빈 항목을 채워 주세요.',key)
        else: add(label+'의 필요 여부를 정해 주세요.','apply_'+key)
    scenarios=item.get('scenarios',[])
    if not scenarios: add('완료 확인 예시를 최소 한 개 작성해 주세요.','scenarios')
    elif any(not all(str(s.get(k,'')).strip() for k in ['given','when','then']) or s.get('agreement')!='합의' for s in scenarios):
        add('완료 확인 예시의 상황·행동·결과를 작성하고 합의해 주세요.','scenarios')
    if any(d.get('status')!='결정' for d in item.get('decisions',[])): add('미정인 질문의 답변을 확정해 주세요.','decisions')
    return {'ready':not gaps,'gaps':gaps}

def markdown(item):
    lines = [f"# {item['id']} · {item['title']}", '', f"버전 {item['version']} | {item['status']} | {item['priority']}",
             f"저장: {item['updatedAt']} / {item['updatedBy']}", '']
    names = {'project':'프로젝트','owner':'담당자','due':'기한','nextAction':'다음 할 일','need':'필요한 이유',
             'story':'사용자 이야기','scope':'범위','excluded':'제외 사유','source':'출처','flow':'전체 흐름',
             'cta':'화면 행동·CTA','object':'업무 객체','states':'상태 전이','dataFlow':'데이터 흐름',
             'responsibility':'권한·책임','approvalFlow':'업무 승인 체계','exceptions':'예외·취소·재처리',
             'migration':'데이터 이관','risk':'위험','successMetric':'성공 기준','design':'디자인 링크',
             'changeReason':'변경 사유','changeImpact':'변경 영향','changeApprover':'변경 승인 주체'}
    for key, label in names.items():
        lines += [f'## {label}', item.get(key) or '미작성', '']
    row_labels = {'id':'ID','rule':'관련 규칙·AC','given':'상황 (Given)','when':'행동·시점 (When)','then':'기대 결과 (Then)',
                  'decision':'연결 결정 ID','agreement':'합의 상태','test':'검수 상태','actual':'실제 결과','tester':'검수자',
                  'testedAt':'검수일','evidence':'근거·증빙','question':'질문','owner':'담당자','due':'기한','status':'상태',
                  'answer':'결정 내용','target':'대상·목표','direction':'방향','timing':'시점·주기','data':'데이터',
                  'failure':'실패 처리','fallback':'대체 절차','what':'측정 항목','who':'대상 기준','where':'측정 위치','verify':'검증 방법'}
    for key, label in [('scenarios','BDD 검수 시나리오'),('decisions','결정사항'),('interfaces','연동'),('nfr','비기능 요건')]:
        lines += [f'## {label}']
        for row in item[key]:
            lines += [''] + [f'- **{row_labels.get(k,k)}**: {v or "미작성"}' for k,v in row.items()]
        if not item[key]:
            lines += ['미작성']
        lines += ['']
    lines += ['## 6대 누락 점검'] + [f"- {k}: {v['status']} / {v['evidence']}" for k,v in item['checks'].items()]
    lines += ['', '## 연동·품질 기준 적용 여부', json.dumps(item.get('applicability',{}),ensure_ascii=False),
              '', '## 요건 확정', json.dumps(item.get('signoff'), ensure_ascii=False), '']
    if item.get('schemaVersion')==2:
        for key,label in [('kind','요건 유형'),('expected','완료 기준'),('exceptionDetail','예외 처리'),('policyDetail','정책 질문'),('relations','연결된 요건'),('dataUses','데이터 사용 관계'),('questions','확인 질문'),('projectSnapshot','적용한 프로젝트 공통 기준'),('verification','검수 결과')]:
            lines += ['## '+label,json.dumps(item.get(key),ensure_ascii=False,indent=2),'']
    return '\n'.join(lines)

class Store:
    def __init__(self, data, ai_data=None):
        self.data = data.resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.ai_data = Path(ai_data).resolve() if ai_data else self.data
        self.ai_data.mkdir(parents=True, exist_ok=True)
        self.lock = SharedLock(self.data / '.workspace.lock')
        self.config_file = self.data / 'config.json'
        with self.lock:
            if not self.config_file.exists():
                atomic_json(self.config_file, {'archive': str(self.data / 'archive'), 'users': []})

    def config(self):
        return read_json(self.config_file)

    def archive(self):
        return Path(self.config()['archive'])

    def versions(self, rid):
        if not re.fullmatch(r'REQ-[A-F0-9]{12}', rid):
            raise Problem('요건 ID가 올바르지 않습니다.', 404)
        folder = self.folder(rid)
        return sorted(p for p in folder.glob('v*') if re.fullmatch(r'v\d{6}', p.name) and p.is_dir())

    def folder(self,rid):
        old=self.archive()/rid
        if old.is_dir(): return old
        matches=list(self.archive().glob('projects/PRJ-*/'+rid))
        if len(matches)>1: raise Problem('중복된 요건 폴더를 확인해 주세요.',409)
        return matches[0] if matches else old

    def project_payload(self,payload):
        project=next((p for p in project_model.projects(self) if p['id']==payload.get('projectId')),None)
        if not project: raise Problem('프로젝트를 먼저 선택해 주세요.')
        return dict(payload,project=project['name'],projectSnapshot=project)

    def get(self, rid, version=None):
        versions = self.versions(rid)
        if not versions:
            raise Problem('요건을 찾을 수 없습니다.', 404)
        if version is not None:
            versions = [p for p in versions if p.name == f'v{version:06d}']
            if not versions:
                raise Problem('버전을 찾을 수 없습니다.', 404)
        item=read_json(versions[-1] / 'requirement.json')
        item.setdefault('projectId',project_model.legacy_id(item.get('project') or '미분류 프로젝트'))
        item['readiness']=readiness(item)
        return item

    def list(self):
        archive = self.archive()
        if not archive.is_dir():
            raise Problem('아카이브 경로에 연결할 수 없습니다. 관리자에게 문의해 주세요.', 503)
        return sorted([self.get(p.name) for p in project_model.requirement_folders(archive) if p.is_dir() and re.fullmatch(r'REQ-[A-F0-9]{12}', p.name) and self.versions(p.name)], key=lambda i:i['updatedAt'], reverse=True)

    def save(self, payload, user, rid=None):
        with self.lock:
            old = self.get(rid) if rid else None
            if old and payload.get('version') != old['version']:
                raise Problem('다른 담당자가 먼저 수정했습니다. 내용을 복사한 뒤 다시 열어 주세요.', 409)
            if old and old.get('schemaVersion')==2 and payload.get('schemaVersion')!=2:
                raise Problem('최신 프로젝트 화면에서 수정해 주세요.')
            if payload.get('schemaVersion')==2:
                payload=self.project_payload(payload)
                if old and old['projectId']!=payload['projectId']: raise Problem('기존 요건의 소속 프로젝트를 임의로 변경할 수 없습니다.')
            item = validate(payload, self.config()['users'])
            project_model.validate_relations(self,item,rid,Problem)
            was_signed = bool(old and (old.get('signoff') or old.get('everSigned')))
            if was_signed and not all(item[k] for k in ['changeReason','changeImpact','changeApprover']):
                raise Problem('확정 이후 수정에는 변경 사유·영향 범위·승인 주체가 필요합니다.')
            if was_signed and user['role'] != 'admin':
                raise Problem('확정 요건 변경은 관리자에게 요청해 주세요.', 403)
            if item['status'] in ['확정','진행','완료']:
                if user['role'] != 'admin':
                    raise Problem('요건 확정·진행·완료 변경은 관리자가 수행합니다.', 403)
                gaps=readiness(item)['gaps']
                if gaps:
                    raise Problem('확정 전 보완이 필요합니다: ' + ' / '.join(g['label'] for g in gaps))
                if item.get('schemaVersion')!=2 and (not item['source'] or not item['scenarios'] or any(d['status']=='미정' for d in item['decisions']) or any(s['agreement']!='합의' for s in item['scenarios']) or any(c['status']=='미정' for c in item['checks'].values())):
                    raise Problem('확정 전에 출처·BDD 합의·정책 결정·6대 점검을 완료해 주세요.')
                if any(not all(row.values()) for row in item['nfr']):
                    raise Problem('확정 전에 비기능 요건의 여섯 가지 측정 기준을 모두 작성해 주세요.')
                if item['status']=='완료' and any(s['test']!='통과' for s in item['scenarios']):
                    raise Problem('완료 처리 전 모든 BDD 시나리오 검수가 통과해야 합니다.')
                if item.get('schemaVersion')==2 and item['status']=='완료':
                    v=item['verification']
                    if v['status']!='통과' or not all(v[k] for k in ['actual','tester','date','evidence']): raise Problem('완료 전에 실제 결과·검수자·날짜·증빙을 남겨 주세요.')
                    date(v['date'])
                item['signoff'] = {'by': user['username'], 'name': user['name'], 'at': now(), 'version': (old['version']+1 if old else 1)}
            else:
                item['signoff'] = None
            item['everSigned'] = was_signed or bool(item['signoff'])
            item.update(id=rid or 'REQ-'+secrets.token_hex(6).upper(), version=old['version']+1 if old else 1,
                        createdAt=old['createdAt'] if old else now(), createdBy=old['createdBy'] if old else user['username'],
                        updatedAt=now(), updatedBy=user['username'])
            archive = self.archive()
            if not archive.is_dir():
                raise Problem('아카이브가 연결되지 않아 저장하지 못했습니다.', 503)
            folder = self.folder(item['id']) if old else (archive/'projects'/item['projectId']/item['id'] if item.get('schemaVersion')==2 else archive/item['id'])
            folder.mkdir(parents=True,exist_ok=True)
            stage = folder / ('.pending-'+secrets.token_hex(8))
            final = folder / f"v{item['version']:06d}"
            stage.mkdir()
            try:
                atomic_json(stage/'requirement.json', item)
                with (stage/'requirement.md').open('x', encoding='utf-8') as f:
                    f.write(markdown(item)); f.flush(); os.fsync(f.fileno())
                os.rename(stage, final)
            except FileExistsError:
                raise Problem('동시 수정이 감지되었습니다. 다시 열어 주세요.', 409)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
            item['readiness']=readiness(item)
            return item

class Handler(BaseHTTPRequestHandler):
    server_version = 'Requirements/1.0'
    def log_message(self, fmt, *args):
        pass

    def send(self, data, status=200, headers=None, kind='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False).encode() if kind.startswith('application/json') else data
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k,v in (headers or {}).items():
            self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)

    def body(self):
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
            raise Problem('JSON 요청이 필요합니다.', 415)
        size = int(self.headers.get('Content-Length','0'))
        limit = 16_000_000 if re.fullmatch(r'/api/requirements(?:/REQ-[A-F0-9]{12})?',urlsplit(self.path).path) else 1_000_000
        if not 0 < size <= limit:
            raise Problem('요청 크기를 확인해 주세요.', 413)
        value = json.loads(self.rfile.read(size))
        if not isinstance(value, dict):
            raise Problem('객체 형식의 요청이 필요합니다.')
        return value

    def session(self):
        cookie = SimpleCookie(self.headers.get('Cookie',''))
        token = cookie.get('session')
        sess = SESSIONS.get(token.value if token else '', {})
        if sess.get('expires',0) < time.time():
            raise Problem('로그인이 필요합니다.', 401)
        user = next((u for u in self.server.store.config()['users'] if u['username']==sess['username']), None)
        if not user:
            raise Problem('로그인이 필요합니다.', 401)
        return user, sess

    def handle_request(self):
        store = self.server.store
        path = urlsplit(self.path).path
        if self.command == 'GET' and path in ['/', '/app.js', '/style.css', '/design.css', '/guide-polish.css', '/guidance.js', '/workspace.js', '/ai-guide.js', '/relationships.js', '/PretendardVariable.woff2']:
            name, kind = {'/':('index.html','text/html; charset=utf-8'), '/app.js':('app.js','text/javascript; charset=utf-8'), '/style.css':('style.css','text/css; charset=utf-8'), '/design.css':('design.css','text/css; charset=utf-8'), '/guide-polish.css':('guide-polish.css','text/css; charset=utf-8'), '/guidance.js':('guidance.js','text/javascript; charset=utf-8'), '/workspace.js':('workspace.js','text/javascript; charset=utf-8'), '/ai-guide.js':('ai-guide.js','text/javascript; charset=utf-8'), '/relationships.js':('relationships.js','text/javascript; charset=utf-8'), '/PretendardVariable.woff2':('PretendardVariable.woff2','font/woff2')}[path]
            return self.send((ROOT/'static'/name).read_bytes(), kind=kind)
        if path == '/api/bootstrap' and self.command == 'GET':
            return self.send({'instance':getattr(self.server,'instance_id',''), 'setup': not store.config()['users'], 'local': self.client_address[0] in ['127.0.0.1','::1']})
        body = {}
        if self.command in ['POST','PUT']:
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                raise Problem('다른 사이트에서 보낸 요청은 허용되지 않습니다.', 403)
            body = self.body()
        if path in ['/api/setup','/api/login'] and self.command == 'POST':
            with store.lock:
                config = store.config()
                if path.endswith('setup'):
                    if config['users'] or self.client_address[0] not in ['127.0.0.1','::1']:
                        raise Problem('최초 관리자 설정은 서버 PC에서 한 번만 가능합니다.', 403)
                    user = self.new_user(body, 'admin')
                    archive = Path(config['archive']); archive.mkdir(exist_ok=True)
                    config['users'].append(user); atomic_json(store.config_file,config)
                else:
                    ip = self.client_address[0]
                    times = [t for t in ATTEMPTS.get(ip,[]) if t > time.time()-300]
                    ATTEMPTS[ip] = times
                    if len(times)>=10:
                        raise Problem('로그인 시도가 많습니다. 5분 뒤 다시 시도해 주세요.',429)
                    user = next((u for u in config['users'] if u['username']==body.get('username')),None)
                    passwd = text(body.get('password',''),256)
                    if not user or not hmac.compare_digest(password_hash(passwd, user['hash'].split(':')[0]),user['hash']):
                        times.append(time.time()); raise Problem('아이디 또는 비밀번호를 확인해 주세요.',401)
                    ATTEMPTS.pop(ip,None)
                token = secrets.token_urlsafe(32)
                csrf = secrets.token_urlsafe(32)
                SESSIONS[token] = {'username':user['username'], 'expires':time.time()+28800, 'csrf':csrf}
                secure = '; Secure' if self.server.secure_cookie else ''
                return self.send({'user':user_public(user),'csrf':csrf},headers={'Set-Cookie':f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}'})
        user, sess = self.session()
        if self.command in ['POST','PUT'] and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),sess['csrf']):
            raise Problem('화면을 새로고침한 뒤 다시 시도해 주세요.',403)
        if path == '/api/me':
            return self.send({'user':user_public(user),'csrf':sess['csrf']})
        if path == '/api/logout' and self.command == 'POST':
            for key in list(SESSIONS):
                if SESSIONS[key] is sess: del SESSIONS[key]
            return self.send({'ok':True},headers={'Set-Cookie':'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
        if path == '/api/users':
            if self.command == 'POST':
                self.admin(user)
                with store.lock:
                    config = store.config(); new = self.new_user(body,body.get('role','member'))
                    if any(u['username']==new['username'] for u in config['users']):
                        raise Problem('이미 사용 중인 아이디입니다.')
                    config['users'].append(new); atomic_json(store.config_file, config)
            return self.send([user_public(u) for u in store.config()['users']])
        if path == '/api/settings':
            self.admin(user)
            if self.command == 'PUT':
                folder = Path(text(body.get('archive',''),1000))
                if not folder.is_absolute() or not folder.is_dir():
                    raise Problem('존재하는 절대 폴더 경로를 입력해 주세요. 공유폴더는 UNC 경로를 사용하세요.')
                with store.lock:
                    config=store.config()
                    if Path(config['archive']).resolve() != folder.resolve() and (any(store.archive().glob('REQ-*')) or any((store.archive()/'projects').glob('PRJ-*'))):
                        raise Problem('기존 요건이 있습니다. 서버를 중지하고 전체 아카이브를 새 경로로 복사한 뒤 config.json을 변경해 주세요.')
                    probe=folder/('.req-write-probe-'+secrets.token_hex(8))
                    probe.write_text('write-test',encoding='utf-8'); probe.unlink()
                    config['archive']=str(folder); atomic_json(store.config_file,config)
            return self.send({'archive':str(store.archive()), 'connected':store.archive().is_dir()})
        if path.startswith('/api/ai/') or re.fullmatch(r'/api/projects/PRJ-[A-F0-9]{12}/guide/.*',path):
            return ai_guide.route(self,path,body,user,store,Problem,atomic_json,now,store.lock)
        if path == '/api/check' and self.command == 'POST':
            if body.get('schemaVersion')==2: body=store.project_payload(body)
            return self.send(readiness(body))
        if path == '/api/projects':
            if self.command=='GET': return self.send(project_model.projects(store))
            if self.command=='POST':
                self.admin(user)
                with store.lock: return self.send(project_model.save_project(store,body,user,None,Problem,atomic_json,now),201)
        export_match=re.fullmatch(r'/api/projects/(PRJ-[A-F0-9]{12})/export',path)
        if export_match and self.command=='GET':
            project_id=export_match[1]
            with store.lock:
                if not any(p['id']==project_id for p in project_model.projects(store)):
                    raise Problem('프로젝트를 찾을 수 없습니다.',404)
                items=[r for r in store.list() if r.get('projectId')==project_id]
            if not items: raise Problem('다운로드할 저장된 요건이 없습니다.',404)
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
                for item in sorted(items,key=lambda r:r['id']):
                    title=re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_',item['title']).strip('. ')[:80] or '요건'
                    archive.writestr(f'{item["id"]}_{title}_v{item["version"]}.md',markdown(item).encode('utf-8'))
            return self.send(output.getvalue(),kind='application/zip',headers={'Content-Disposition':f'attachment; filename="{project_id}-requirements.zip"'})
        project_match=re.fullmatch(r'/api/projects/(PRJ-[A-F0-9]{12})',path)
        if project_match and self.command=='PUT':
            self.admin(user)
            with store.lock: return self.send(project_model.save_project(store,body,user,project_match[1],Problem,atomic_json,now))
        if path == '/api/requirements':
            if self.command == 'GET': return self.send(store.list())
            if self.command == 'POST': return self.send(store.save(body,user),201)
        match=re.fullmatch(r'/api/requirements/(REQ-[A-F0-9]{12})(?:/(history|export)(?:/(\d+))?)?',path)
        if match:
            rid, action, ver=match.groups()
            if self.command == 'PUT' and not action: return self.send(store.save(body,user,rid))
            if self.command == 'GET':
                if action == 'history':
                    return self.send([read_json(p/'requirement.json') for p in reversed(store.versions(rid))])
                item=store.get(rid,int(ver) if ver else None)
                if action == 'export':
                    return self.send(markdown(item).encode(),kind='text/markdown; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="{rid}-v{item["version"]}.md"'})
                return self.send(item)
        raise Problem('요청한 경로를 찾을 수 없습니다.',404)

    def admin(self,user):
        if user['role']!='admin': raise Problem('관리자 권한이 필요합니다.',403)

    def new_user(self,body,role):
        username=text(body.get('username',''),50); name=text(body.get('name',''),80); password=text(body.get('password',''),256)
        if not re.fullmatch(r'[A-Za-z0-9._-]{3,50}',username) or not name or len(password)<12 or role not in ['admin','member']:
            raise Problem('아이디는 영문·숫자 등 3자 이상, 이름 필수, 비밀번호는 12자 이상이어야 합니다.')
        return {'username':username,'name':name,'role':role,'hash':password_hash(password)}

    def dispatch(self):
        try: self.handle_request()
        except Problem as e: self.send({'error':e.message},e.status)
        except (ValueError,TypeError,KeyError,AttributeError): self.send({'error':'입력 또는 저장 데이터 형식을 확인해 주세요.'},400)
        except OSError: self.send({'error':'저장소 읽기·쓰기 실패입니다. 공유폴더 연결 및 실행 계정의 권한을 확인해 주세요. 저장 성공으로 처리되지 않았습니다.'},503)
    do_GET = do_POST = do_PUT = dispatch

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data',type=Path,default=ROOT/'data')
    parser.add_argument('--instance-id',default='')
    parser.add_argument('--ai-data',type=Path,default=None)
    parser.add_argument('--secure-cookie',action='store_true')
    args=parser.parse_args()
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    server.instance_id=args.instance_id
    server.store=Store(args.data,args.ai_data); server.secure_cookie=args.secure_cookie
    print(f'Requirements: http://{args.host}:{args.port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=='__main__': main()
