"""Official installed CLI adapters. Credentials stay with each CLI."""
import json
import os
import shutil
import subprocess
import tempfile
import queue
import threading
import re
import time
from pathlib import Path

FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
LOGIN_TASKS = {}
LOGIN_LOCK = threading.Lock()

def model_value(value, Problem):
    if not isinstance(value,str) or (value and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:()/-]{0,99}',value)):
        raise Problem('모델 이름을 확인해 주세요.')
    return value

def codex_info(exe):
    """Read only public account metadata/model catalog via the official RPC protocol."""
    with tempfile.TemporaryDirectory(prefix='requirements-status-') as temp:
        p=subprocess.Popen([exe,'app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            encoding='utf-8',errors='replace',cwd=temp,creationflags=FLAGS)
        messages=queue.Queue()
        def reader():
            for line in p.stdout:
                try: messages.put(json.loads(line))
                except ValueError: pass
        thread=threading.Thread(target=reader,daemon=True);thread.start()
        def rpc(ident,method,params):
            p.stdin.write(json.dumps({'id':ident,'method':method,'params':params})+'\n');p.stdin.flush()
            end=time.monotonic()+15
            while time.monotonic()<end:
                event=messages.get(timeout=max(.01,end-time.monotonic()))
                if event.get('id')==ident:
                    if 'error' in event: raise ValueError('RPC failed')
                    return event['result']
            raise ValueError('RPC timeout')
        try:
            rpc(1,'initialize',{'clientInfo':{'name':'requirements_workspace','version':'0.3.0'}})
            p.stdin.write('{"method":"initialized"}\n');p.stdin.flush()
            account=rpc(2,'account/read',{'refreshToken':False}).get('account')
            models=rpc(3,'model/list',{'limit':100,'includeHidden':False}).get('data',[])
            return {'loggedIn':bool(account),'account':(account or {}).get('email') or (account or {}).get('type',''),
                'models':[{'id':m['model'],'name':m.get('displayName') or m['model']} for m in models if m.get('model')],
                'modelNote':'Codex가 반환한 모델 목록입니다. 실제 사용 가능 여부는 연결 시험으로 확인합니다.'}
        finally:
            p.kill();p.wait();thread.join(timeout=2);p.stdin.close();p.stdout.close()

def account_info(provider,Problem):
    exe=executable(provider)
    if not exe: raise Problem('먼저 선택한 AI의 공식 CLI를 설치해 주세요.',503)
    try:
        if provider=='codex': result=codex_info(exe)
        else:
            p=subprocess.run([exe,'auth','status','--json'],capture_output=True,encoding='utf-8',errors='replace',timeout=15,creationflags=FLAGS)
            value=json.loads(p.stdout)
            result={'loggedIn':bool(value.get('loggedIn')),'account':value.get('email') or value.get('authMethod',''),
                'models':[{'id':x,'name':x.capitalize()} for x in ['sonnet','opus','haiku']],
                'modelNote':'Claude 공식 모델 별칭입니다. 계정·조직의 허용 목록 조회 결과는 아니며 연결 시험으로 확인합니다.'}
    except (OSError,ValueError,KeyError,TypeError,queue.Empty,subprocess.TimeoutExpired):
        raise Problem('계정·모델 정보를 읽지 못했습니다. CLI를 업데이트한 뒤 다시 확인해 주세요.',503)
    with LOGIN_LOCK:
        task=LOGIN_TASKS.get(provider,{})
        result['loginState']=task.get('state','idle')
    return result

def start_login(provider,Problem):
    exe=executable(provider)
    if not exe: raise Problem('선택한 AI의 CLI를 먼저 설치하세요.',503)
    args=[exe,'login'] if provider=='codex' else [exe,'auth','login']
    with LOGIN_LOCK:
        if LOGIN_TASKS.get(provider,{}).get('state')=='running': return {'state':'running'}
        LOGIN_TASKS[provider]={'state':'running'}
    def run():
        try:
            # Both official commands own the browser OAuth flow; discard auth output.
            with tempfile.TemporaryDirectory(prefix='requirements-login-') as temp:
                p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    cwd=temp,timeout=180,creationflags=FLAGS)
            state='completed' if p.returncode==0 else 'failed'
        except (OSError,subprocess.TimeoutExpired): state='failed'
        with LOGIN_LOCK: LOGIN_TASKS[provider]={'state':state}
    threading.Thread(target=run,daemon=True).start()
    return {'state':'running'}

def executable(provider):
    name={'codex':'codex','claude':'claude'}.get(provider)
    if not name: return None
    found=shutil.which(name+'.exe' if os.name=='nt' else name)
    if found: return found
    home=Path.home()
    choices=[home/'.local/bin'/f'{name}.exe',home/'.cargo/bin'/f'{name}.exe']
    if provider=='codex': choices+=sorted((home/'AppData/Local/OpenAI/Codex/bin').glob('*/codex.exe'),key=lambda p:p.stat().st_mtime,reverse=True)
    return next((str(p) for p in choices if p.is_file()),None)

def available():
    return [{'id':p,'name':label,'installed':bool(executable(p))} for p,label in [('codex','Codex'),('claude','Claude Code')]]

def invoke(provider,context,prompt,schema,Problem,model=''):
    model=model_value(model,Problem)
    exe=executable(provider)
    if not exe: raise Problem('선택한 AI의 CLI를 찾지 못했습니다. 설치 후 요건작업실을 다시 실행하세요.',503)
    with tempfile.TemporaryDirectory(prefix='requirements-ai-') as temp:
        folder=Path(temp);schema_file=folder/'schema.json';output=folder/'result.json'
        schema_file.write_text(json.dumps(schema),encoding='utf-8')
        if provider=='codex':
            args=[exe,'exec','--ignore-user-config','--skip-git-repo-check','--ephemeral','--sandbox','read-only',
                '--disable','shell_tool','--disable','unified_exec','--disable','multi_agent',
                '--disable','skill_search','--enable','skip_host_skill_discovery','-c','web_search="disabled"',
                '--output-schema',str(schema_file),'--output-last-message',str(output),'-']
        else:
            # Safe mode retains login (unlike --bare), but omits custom hooks/skills.
            args=[exe,'--print','--safe-mode','--strict-mcp-config','--tools','',
                '--permission-mode','dontAsk','--no-session-persistence','--output-format','json','--json-schema',json.dumps(schema)]
        if model:
            if provider=='codex': args[-1:-1]=['--model',model]
            else: args+=['--model',model]
        message=prompt+'\n도구를 사용하지 말고 제공된 자료만 분석하세요. JSON으로만 응답하세요.\n'+json.dumps(context,ensure_ascii=False)
        try:
            proc=subprocess.run(args,input=message,encoding='utf-8',errors='replace',capture_output=True,cwd=folder,timeout=180,creationflags=FLAGS)
        except subprocess.TimeoutExpired: raise Problem('AI 처리가 3분 안에 완료되지 않았습니다. 모델 응답 지연 또는 연결 상태를 확인해 주세요. 기존 대화와 초안은 변경되지 않았습니다.',504)
        except OSError: raise Problem('설치된 AI를 실행하지 못했습니다. CLI 설치 상태를 확인하세요.',503)
        def context_limit(value):
            return any(t in str(value).lower() for t in ['context_length_exceeded','maximum context length','context window exceeded','prompt is too long','prompt too long'])
        if proc.returncode:
            if context_limit(getattr(proc,'stderr','')+' '+getattr(proc,'stdout','')): raise Problem('AI 컨텍스트 한도를 초과했습니다.',502)
            raise Problem('AI 호출에 실패했습니다. 선택한 CLI의 로그인·사용 한도·업데이트 상태를 확인하세요.',502)
        try:
            if provider=='codex': return json.loads(output.read_text(encoding='utf-8'))
            result=json.loads(proc.stdout)
            if result.get('is_error'):
                if context_limit(result.get('result','')): raise Problem('AI 컨텍스트 한도를 초과했습니다.',502)
                raise ValueError()
            return result['structured_output']
        except (ValueError,OSError,KeyError,TypeError): raise Problem('AI의 구조화 응답을 읽지 못했습니다. CLI를 업데이트하고 다시 연결해 주세요.',502)
