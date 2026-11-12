"""Project workspaces and proportional requirement completion rules."""
import hashlib
import json
import os
import re
import secrets
from pathlib import Path

NARRATIVE_LIMIT = None
NARRATIVE_FIELDS = {'need','flow','scope','states','responsibility','expected','exceptionDetail','policyDetail'}

def legacy_id(name):
    return 'PRJ-'+hashlib.sha256(name.encode()).hexdigest()[:12].upper()

def requirement_folders(archive):
    return list(archive.glob('REQ-*'))+list(archive.glob('projects/PRJ-*/REQ-*'))

def projects(store):
    result={}
    for folder in requirement_folders(store.archive()):
        versions=sorted(folder.glob('v[0-9][0-9][0-9][0-9][0-9][0-9]/requirement.json'))
        if not versions: continue
        item=json.loads(versions[-1].read_text(encoding='utf-8'))
        name=item.get('project') or '미분류 프로젝트'
        pid=item.get('projectId') or legacy_id(name)
        result.setdefault(pid,{'id':pid,'name':name,'version':0,'defaultOwner':item['owner'],'description':'기존 요건에서 연결한 프로젝트','commonRules':'','qualityCriteria':'','legacy':True})
    for folder in (store.archive()/'projects').glob('PRJ-*'):
        versions=sorted(folder.glob('settings/v[0-9][0-9][0-9][0-9][0-9][0-9].json'))
        if versions:
            item=json.loads(versions[-1].read_text(encoding='utf-8'));result[item['id']]=item
    return sorted(result.values(),key=lambda p:p['name'])

def save_project(store,payload,user,pid,Problem,atomic_json,now):
    all_projects=projects(store)
    old=next((p for p in all_projects if p['id']==pid),None) if pid else None
    if pid and not old: raise Problem('프로젝트를 찾을 수 없습니다.',404)
    if old and payload.get('version')!=old['version']: raise Problem('프로젝트 설정이 변경되었습니다. 다시 열어 주세요.',409)
    item={}
    for key in ['name','description','defaultOwner','commonRules','qualityCriteria']:
        value=payload.get(key,'')
        if not isinstance(value,str): raise Problem('프로젝트 입력 형식을 확인해 주세요.')
        item[key]=value.strip()
    if not item['name']: raise Problem('프로젝트 이름을 입력해 주세요.')
    if item['defaultOwner'] not in [u['username'] for u in store.config()['users']]: raise Problem('기본 담당자를 선택해 주세요.')
    if any(p['id']!=pid and p['name']==item['name'] for p in all_projects): raise Problem('같은 이름의 프로젝트가 있습니다.')
    item.update(id=pid or 'PRJ-'+secrets.token_hex(6).upper(),version=old['version']+1 if old else 1,updatedAt=now(),updatedBy=user['username'])
    if not store.archive().is_dir(): raise Problem('아카이브 연결을 확인해 주세요.',503)
    folder=store.archive()/'projects'/item['id']/'settings';folder.mkdir(parents=True,exist_ok=True)
    final=folder/f"v{item['version']:06d}.json"
    if final.exists(): raise Problem('같은 버전이 이미 저장되었습니다.',409)
    atomic_json(final,item)
    return item

def normalize(payload,item,Problem):
    item['schemaVersion']=2
    for key,fields in {'relations':['requirementId','type','reason','status'], 'dataUses':['name','operation','description','status']}.items():
        rows=payload.get(key,[])
        if not isinstance(rows,list): raise Problem('연결 정보는 목록이어야 합니다.')
        item[key]=[]
        seen=set()
        for row in rows:
            if not isinstance(row,dict): raise Problem('연결 정보 형식을 확인해 주세요.')
            entry={}
            for field in fields:
                value=row.get(field,'제안' if field=='status' else '')
                if not isinstance(value,str): raise Problem('연결 정보 입력 형식을 확인해 주세요.')
                entry[field]=value.strip()
            if entry['status'] not in ['제안','확인']: raise Problem('연결 정보의 확인 상태를 선택해 주세요.')
            if key=='relations':
                if not re.fullmatch(r'REQ-[A-F0-9]{12}',entry['requirementId']) or entry['type'] not in ['선행 필요','관련']: raise Problem('연결할 요건과 관계를 선택해 주세요.')
                version=row.get('targetVersion',0)
                if not isinstance(version,int) or isinstance(version,bool) or version<0: raise Problem('연결 버전을 확인해 주세요.')
                entry['targetVersion']=version
                identity=(entry['requirementId'],entry['type'])
            else:
                entry['name']=' '.join(entry['name'].split())
                if not entry['name'] or entry['operation'] not in ['생성','조회','변경','삭제']: raise Problem('데이터 이름과 사용 방식을 선택해 주세요.')
                identity=(entry['name'].casefold(),entry['operation'])
            if identity in seen: raise Problem('같은 연결 정보가 중복되었습니다.')
            seen.add(identity);item[key].append(entry)
    item['kind']=payload.get('kind','기능 변경')
    if item['kind'] not in ['화면·문구 수정','기능 변경','업무·정책 변경']: raise Problem('요건 유형을 확인해 주세요.')
    for key in ['expected','exceptionDetail','policyDetail']:
        value=payload.get(key,'')
        if not isinstance(value,str): raise Problem(f'{key}: 문자열을 입력해 주세요.')
        item[key]=value.strip()
    questions=payload.get('questions',{})
    if not isinstance(questions,dict): raise Problem('확인 질문 형식을 확인해 주세요.')
    item['questions']={}
    for key in ['exceptions','interfaces','policy']:
        value=questions.get(key,'모르겠어요')
        if value not in ['없어요','있어요','모르겠어요']: raise Problem('확인 질문의 답변을 선택해 주세요.')
        item['questions'][key]=value
    verification=payload.get('verification',{})
    if not isinstance(verification,dict): raise Problem('검수 기록 형식을 확인해 주세요.')
    item['verification']={}
    for key in ['status','actual','tester','date','evidence']:
        value=verification.get(key,'미실시' if key=='status' else '')
        if not isinstance(value,str): raise Problem('검수 기록 형식을 확인해 주세요.')
        item['verification'][key]=value.strip()
    if item['verification']['status'] not in ['미실시','통과','실패','보류']: raise Problem('검수 상태를 확인해 주세요.')

def readiness(item):
    gaps=[]
    def add(label,target): gaps.append({'label':label,'target':target})
    for key in ['relations','dataUses']:
        if any(r.get('status')!='확인' for r in item.get(key,[])): add('제안된 요건·데이터 연결을 확인하거나 제외해 주세요.',key)
    for key,label in [('title','필요한 기능'),('need','필요한 이유'),('flow','언제 어떻게 동작하는지'),('expected','완료 기준')]:
        if not str(item.get(key,'')).strip(): add(label+'를 적어 주세요.',key)
    for key,label in [('exceptions','예외 상황'),('interfaces','다른 시스템 연결'),('policy','아직 정하지 못한 정책')]:
        answer=item.get('questions',{}).get(key,'모르겠어요')
        if answer=='모르겠어요': add(label+'을 담당자와 확인해 주세요.','q_'+key)
        elif answer=='있어요':
            if key=='exceptions' and not item.get('exceptionDetail'): add('예외 상황과 처리 결과를 적어 주세요.','exceptionDetail')
            if key=='interfaces':
                rows=item.get('interfaces',[])
                if not rows or any(not all(str(r.get(k,'')).strip() for k in ['target','direction','timing','data','failure','fallback','owner']) for r in rows): add('연결 대상·데이터·실패 처리·담당자를 정리해 주세요.','interfaces')
            if key=='policy' and (not item.get('policyDetail') or not item.get('decisions')): add('정책 질문과 결정 기록을 남겨 주세요.','decisions')
        elif key=='interfaces' and item.get('interfaces'): add('연동 기록이 있습니다. 연결 여부를 확인해 주세요.','q_interfaces')
        elif key=='exceptions' and item.get('exceptionDetail'): add('예외 기록이 있습니다. 예외 여부를 확인해 주세요.','q_exceptions')
        elif key=='policy' and item.get('policyDetail'): add('정책 기록이 있습니다. 정책 여부를 확인해 주세요.','q_policy')
    if item.get('kind')=='업무·정책 변경':
        for key,label in [('scope','변경 범위'),('states','업무 상태와 변경 조건')]:
            if not item.get(key): add(label+'를 적어 주세요.',key)
        if not item.get('responsibility') and not item.get('projectSnapshot',{}).get('commonRules'):
            add('프로젝트 공통 규칙 또는 이 요건의 권한·책임을 정해 주세요.','responsibility')
    if any(d.get('status')!='결정' or not all(d.get(k) for k in ['question','owner','due','answer','evidence']) for d in item.get('decisions',[])): add('정책 질문의 답변과 근거를 확정해 주세요.','decisions')
    if any(s.get('agreement')!='합의' or not all(s.get(k) for k in ['given','when','then']) for s in item.get('scenarios',[])): add('추가한 완료 예시를 합의해 주세요.','scenarios')
    if any(not all(str(r.get(k,'')).strip() for k in ['what','who','when','where','target','verify']) for r in item.get('nfr',[])): add('추가한 품질 기준의 측정 조건을 채워 주세요.','nfr')
    return {'ready':not gaps,'gaps':gaps}

def validate_relations(store,item,rid,Problem):
    """References are real project-local IDs; version stamps survive later edits."""
    if not item.get('relations'): return
    all_items={r['id']:r for r in store.list()}
    for relation in item['relations']:
        target=all_items.get(relation['requirementId'])
        if not target or target.get('projectId')!=item.get('projectId'): raise Problem('같은 프로젝트에 등록된 요건만 연결할 수 있습니다.')
        if target['id']==rid: raise Problem('자기 자신을 선행 요건으로 연결할 수 없습니다.')
        if relation['targetVersion']>target['version']: raise Problem('연결 대상 버전이 올바르지 않습니다.')
        if not relation['targetVersion']: relation['targetVersion']=target['version']
    # A confirmed prerequisite chain cannot lead back to this requirement.
    if rid:
        all_items[rid]=item
        visited=set()
        def visit(node,path):
            if node in path: raise Problem('선행 요건이 서로 순환합니다. 연결 방향을 확인해 주세요.')
            if node in visited: return
            for edge in all_items.get(node,{}).get('relations',[]):
                if edge['type']=='선행 필요' and edge['status']=='확인': visit(edge['requirementId'],path|{node})
            visited.add(node)
        visit(rid,set())

