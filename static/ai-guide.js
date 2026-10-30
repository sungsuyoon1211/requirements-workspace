'use strict';
let guideSession=null,guideSources=[],guideSessions=[],guideStatus={},guideEpoch=0;
const guidePath=()=>'/projects/'+selectedProject+'/guide/';
const guideLabels={title:'필요한 기능',need:'필요한 이유',flow:'동작 흐름',expected:'완료 기준',scope:'범위',states:'업무 상태',responsibility:'권한·책임',exceptionDetail:'예외 처리',policyDetail:'확인할 정책'};
function guideSessionLabel(session,sessions=guideSessions){
 const byId=new Map(sessions.map(x=>[x.id,x]));let root=session,number=1;const visited=new Set([session.id]);
 while(root.continuedFrom&&byId.has(root.continuedFrom)&&!visited.has(root.continuedFrom)){
  root=byId.get(root.continuedFrom);visited.add(root.id);number++;
 }
 const title=root.result?.draft?.title||root.baseRequirement?.title||session.result?.draft?.title||session.baseRequirement?.title||'아직 제목 없는 대화';
 const chained=number>1||session.continuedTo||sessions.some(x=>x.continuedFrom===session.id);
 return title+(chained?' '+number:'');
}
const guideOrderKey=()=>`requirements-chat-order:${me.username}:${selectedProject}`;
function orderedGuideSessions(){
 const recent=guideSessions.slice().sort((a,b)=>(b.createdAt||'').localeCompare(a.createdAt||'')||b.id.localeCompare(a.id));
 let saved=[];try{const value=JSON.parse(localStorage.getItem(guideOrderKey())||'[]');if(Array.isArray(value))saved=value.filter(x=>typeof x==='string')}catch{}
 const rank=new Map(saved.map((id,i)=>[id,i]));
 return recent.sort((a,b)=>(rank.get(a.id)??-1)-(rank.get(b.id)??-1));
}
function enableGuideReorder(side){
 const cards=[...side.querySelectorAll('[data-session]')];if(!cards.length)return;
 const list=document.createElement('div');list.className='guide-session-list';list.setAttribute('role','group');list.setAttribute('aria-label','내 작성 대화 · 드래그 또는 Alt와 위아래 방향키로 순서 변경');cards[0].before(list);cards.forEach(card=>list.append(card));
 const hint=document.createElement('p');hint.className='help guide-order-hint';hint.textContent='⋮⋮ 드래그로 순서 변경 · Alt + ↑ ↓';list.before(hint);
 let dragging=null,suppressClickUntil=0;
 const clear=()=>{cards.forEach(x=>x.classList.remove('drop-before','drop-after','is-dragging'));dragging=null};
 const save=()=>{try{localStorage.setItem(guideOrderKey(),JSON.stringify([...list.querySelectorAll('[data-session]')].map(x=>x.dataset.session)));toast('대화 순서를 저장했어요.')}catch{toast('이 브라우저에서 순서를 저장하지 못했습니다. 저장소 설정을 확인해 주세요.')}};
 cards.forEach(card=>{
  card.draggable=true;card.title='드래그하거나 Alt + 위·아래 방향키로 이동';
  card.addEventListener('click',e=>{if(Date.now()<suppressClickUntil){e.preventDefault();e.stopImmediatePropagation()}},true);
  card.addEventListener('dragstart',e=>{if(card.disabled||guideSending){e.preventDefault();return}dragging=card;card.classList.add('is-dragging');e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',card.dataset.session)});
  card.addEventListener('dragover',e=>{if(!dragging||dragging===card||guideSending)return;e.preventDefault();e.dataTransfer.dropEffect='move';cards.forEach(x=>x.classList.remove('drop-before','drop-after'));card.classList.add(e.clientY<card.getBoundingClientRect().top+card.offsetHeight/2?'drop-before':'drop-after')});
  card.addEventListener('drop',e=>{if(!dragging||guideSending)return;e.preventDefault();if(dragging!==card){const after=e.clientY>=card.getBoundingClientRect().top+card.offsetHeight/2;list.insertBefore(dragging,after?card.nextSibling:card);save()}suppressClickUntil=Date.now()+350;clear()});
  card.addEventListener('dragend',()=>{suppressClickUntil=Date.now()+350;clear()});
  card.addEventListener('keydown',e=>{if(!e.altKey||!['ArrowUp','ArrowDown'].includes(e.key)||card.disabled||guideSending)return;e.preventDefault();const neighbor=e.key==='ArrowUp'?card.previousElementSibling:card.nextElementSibling;if(!neighbor)return;list.insertBefore(card,e.key==='ArrowUp'?neighbor:neighbor.nextSibling);card.focus();save()});
 });
}
const guideBaseShell=shell;
shell=function(){guideEpoch++;guideBaseShell();const nav=$('.nav');if(!nav)return;
 const p=projectNow();
 if(p){const b=document.createElement('button');b.textContent='✧ AI와 요건 만들기';b.className=workspaceView==='guide'?'active':'';b.onclick=()=>{workspaceView='guide';shell()};nav.prepend(b)}
 {const b=document.createElement('button');b.textContent='내 PC AI 연결';b.onclick=()=>{workspaceView='ai-setup';shell()};nav.append(b)}
 if(workspaceView==='ai-setup')aiSetup();else if(workspaceView==='guide'&&p)guideHome();
 else if(p&&workspaceView==='requirements') {const b=$('#new');if(b){b.textContent='✧ AI와 요건 만들기';b.onclick=()=>{workspaceView='guide';shell()};const manual=document.createElement('button');manual.textContent='직접 작성';manual.onclick=()=>edit();b.before(manual)}}
};
async function aiSetup(){
 const epoch=guideEpoch,box=$('#content');box.innerHTML='<div class="loading">AI 연결 상태를 확인하고 있어요…</div>';
 try{const s=await api('/ai/status');if(epoch!==guideEpoch)return;
 box.innerHTML=`<div class="hero"><div><div class="eyebrow">TEAM AI SETUP</div><h1>팀의 AI 가이드를 연결해요</h1><p>관리자가 한 번 연결하면 팀원은 별도 키 없이 이용합니다.</p></div><span class="pill">${s.configured?'연결 설정 있음':'아직 연결 전'}</span></div><div class="guide-setup"><section class="panel section formstack"><h2>1. API 이용 준비</h2><p>OpenAI Platform에서 팀용 프로젝트와 API 키를 준비하세요. 결제·사용 한도와 사용할 모델을 해당 계정에서 확인합니다.</p><a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener">API 키 관리 열기 ↗</a><a href="https://developers.openai.com/api/docs/quickstart" target="_blank" rel="noopener">공식 시작 안내 ↗</a><p class="help">키는 이 설정 화면에만 입력하세요. 대화나 프로젝트 자료에 넣지 마세요.</p><h2>2. 연결 시험 후 저장</h2><p>연결 시험은 짧은 API 요청을 실행합니다. 프로젝트 자료는 보내지 않습니다.</p><form id="ai-connect" class="formstack"><label>API 키<input name="key" type="password" autocomplete="new-password" required placeholder="발급받은 API 키를 붙여 넣으세요"><span class="field-guide">서버의 Windows 계정으로 암호화하여 저장합니다. 공유 아카이브와 브라우저에는 보관하지 않습니다.</span></label><label>모델 이름<input name="model" value="${esc(s.model||'gpt-6-astra')}" required placeholder="계정에서 사용 가능한 모델 ID"><span class="field-guide">공식 시작 예시의 모델을 미리 넣었습니다. 계정의 사용 권한과 가격을 확인하고 필요하면 변경하세요.</span></label><button class="primary">연결 확인하고 저장</button></form><div id="connect-result" role="status"></div></section><aside class="panel section formstack"><span class="eyebrow">NEXT STEP</span><h2>3. 프로젝트 자료 준비</h2><p>프로젝트를 선택하고 RFP·회의록을 추가하세요. 자료가 없어도 요구사항 대화부터 시작할 수 있습니다.</p><div class="info">분석을 요청하면 해당 프로젝트의 자료, 기존 요건, 현재 대화가 선택한 AI 서비스로 전달됩니다. 회사에서 외부 AI에 제공할 수 있는 자료를 사용하세요.</div><p>현재 모델: ${esc(s.model||'미설정')}</p><p>최근 연결 시험: ${esc(s.testedAt||'아직 실행하지 않음')}</p><p class="help">Windows 서버 PC에서 설정하세요. 서버 실행 계정이 바뀌면 키를 다시 연결해야 합니다. 현재 버전은 OpenAI 연결을 지원합니다.</p><button id="ai-back">프로젝트로 돌아가기</button></aside></div>`;
 $('#ai-back').onclick=()=>{workspaceView='requirements';shell()};
 $('#ai-connect').onsubmit=async e=>{e.preventDefault();const b=$('button',e.target);b.disabled=true;$('#connect-result').textContent='연결을 확인하고 있어요…';try{await api('/ai/connect','POST',Object.fromEntries(new FormData(e.target)));e.target.reset();if(epoch!==guideEpoch)return;$('#connect-result').textContent='연결 시험과 암호화 저장을 완료했어요. 프로젝트에서 시작하세요.'}catch(error){if(epoch===guideEpoch)$('#connect-result').textContent=error.message}finally{b.disabled=false}};
 }catch(e){if(epoch===guideEpoch)box.textContent=e.message}
}
async function guideHome(){
 const epoch=guideEpoch;$('#content').innerHTML='<div class="loading">프로젝트 자료와 내 대화를 불러오고 있어요…</div>';
 try{const result=await Promise.all([api('/ai/status'),api(guidePath()+'sources'),api(guidePath()+'sessions')]);if(epoch!==guideEpoch)return;[guideStatus,guideSources,guideSessions]=result;
 guideSession=guideSessions.find(s=>s.id===guideSession?.id)||null;drawGuide();
 }catch(e){if(epoch===guideEpoch)$('#content').textContent=e.message}
}
function layoutGuideDraft(){
 const card=$('.guide-draft');if(!card)return;
 const header=document.createElement('header');header.className='guide-draft-header';
 header.append(card.firstElementChild);header.append(card.firstElementChild);
 const body=document.createElement('div');body.className='guide-draft-body';body.tabIndex=0;body.setAttribute('role','region');body.setAttribute('aria-label','함께 정리한 요건 내용');
 const button=$('#guide-review',card),footer=document.createElement('footer');footer.className='guide-draft-footer';
 if(button){const help=button.nextElementSibling;footer.append(button);if(help)footer.append(help)}
 while(card.firstChild)body.append(card.firstChild);
 card.append(header,body);if(button)card.append(footer);else card.classList.add('is-empty');
}
function drawGuide(){
 const s=guideSession,r=s?.result,p=projectNow();
 $('#content').innerHTML=`<div class="hero"><div><div class="eyebrow">${esc(p.name)} · AI GUIDE</div><h1>생각을 말하면, 요건으로 정리해요</h1><p>한 번에 한 가지 질문에 답하세요. 전문적인 요건 정리는 AI가 도와드려요.</p></div><span class="pill">${guideStatus.configured?esc(guideStatus.provider==='claude'?'Claude Code':guideStatus.provider==='codex'?'Codex':'OpenAI API'):'AI 연결 필요'}</span></div>${!guideStatus.configured?`<div class="info guide-notice">자료를 먼저 준비할 수 있어요. 이 PC의 AI를 연결하면 분석을 시작할 수 있어요. <button id="go-ai-setup">내 PC AI 연결하기 →</button></div>`:''}<div class="guide-layout"><aside class="guide-side panel section formstack"><h2>프로젝트 자료</h2><p class="help">팀이 함께 참조합니다. 새 버전은 별도 자료로 추가해 출처를 보존하세요.</p>${guideSources.map(x=>`<details><summary>${esc(x.name)}</summary><p class="help">${esc(x.id)} · ${esc(userName(x.createdBy))}</p><pre class="source-preview">${esc(x.text)}</pre></details>`).join('')||'<p class="muted">RFP나 회의록을 추가하면 맥락에 맞춰 안내해요.</p>'}<details><summary>＋ 자료 추가</summary><form id="guide-source" class="formstack"><label>자료 이름<input name="name" required maxlength="200" placeholder="예: 고객 RFP v1 · 3장 회원 관리"></label><label>파일 선택 · 선택<input id="source-file" type="file" accept=".txt,.md,.docx"><span class="field-guide">TXT·MD·DOCX, 500KB 이하. DOCX는 본문과 표의 텍스트만 읽습니다. PDF·HWP는 아래에 내용을 붙여 넣으세요.</span></label><label>자료 내용 · 파일이 없을 때<textarea name="text" maxlength="60000" placeholder="관련 본문을 붙여 넣으세요. 자료별 최대 6만 자입니다."></textarea></label><button>자료 보관하기</button><p id="source-result" role="status"></p></form></details><hr><h2>내 작성 대화</h2><p class="help">대화는 작성자별로 이어갑니다. 등록된 요건은 팀이 함께 확인합니다.</p><button id="guide-new">＋ 새 요건 시작</button>${orderedGuideSessions().map(x=>`<button class="guide-session ${x.id===s?.id?'selected':''}" data-session="${x.id}">${esc(guideSessionLabel(x))}<small>${x.messages.length/2}회 대화${x.continuedFrom?' · 이어진 대화':''}${x.continuedTo?' · 이전 이력':''}</small></button>`).join('')}<label>기존 요건 보완<select id="guide-existing"><option value="">보완할 요건 선택</option>${localReqs().map(x=>`<option value="${x.id}">${esc(x.title)}</option>`).join('')}</select></label><button id="guide-existing-start">선택 요건으로 시작</button></aside><section class="guide-conversation panel"><div class="section"><span class="eyebrow">${s?'함께 작성 중':'시작 안내'}</span><h2>${esc(r?.draft?.title||s?.baseRequirement?.title||'어떤 업무를 개선하고 싶으세요?')}</h2><p class="help">모르면 ‘모르겠어요’라고 답하세요. 한 번에 여러 내용을 적어도 됩니다.</p></div><div id="guide-messages" class="guide-messages" aria-live="polite">${s?.messages.length?s.messages.map(m=>`<article class="guide-message ${m.role==='user'?'from-user':''}"><strong>${m.role==='user'?'나':'AI 가이드 · 제안'}</strong><p>${guideText(m.text)}</p></article>`).join(''):'<article class="guide-message"><strong>시작 안내</strong><p>예: “자료를 분석해서 요건 후보부터 추천해줘.”<br>또는 “고객이 주문을 취소하는 기능을 만들고 싶어요.”</p></article>'}</div><div class="section formstack"><div class="guide-choices">${(r?.choices||[]).slice(0,3).map((x,i)=>`<button data-choice="${i}">${esc(x)}</button>`).join('')}</div><form id="guide-chat" class="formstack"><label>AI에게 알려줄 내용<textarea id="guide-input" maxlength="6000" required placeholder="필요한 기능이나 질문에 대한 답을 적어 주세요."></textarea></label><div class="row spread"><small>분석 시 프로젝트 자료·요건·대화를 선택한 AI로 전달합니다.</small><button class="primary" ${guideStatus.configured?'':'disabled'}>AI와 이어가기 →</button></div><p id="guide-error" role="status"></p></form></div></section><aside class="guide-draft panel section formstack"><span class="eyebrow">DRAFT · 아직 등록 전</span><h2>함께 정리한 요건</h2>${r?`${Object.entries(guideLabels).filter(([k])=>r.draft[k]).map(([k,label])=>`<div><h3>${label}</h3><p class="preserve-text">${esc(r.draft[k])}</p></div>`).join('')||'<p>분석된 후보에서 하나를 골라 구체화하세요.</p>'}${r.candidates.length?`<h3>자료 기반 요건 후보 · 제안</h3>${r.candidates.map((x,i)=>`<button data-candidate="${i}">${esc(x)}</button>`).join('')}`:''}${r.gaps.length?`<h3>더 확인할 내용</h3><ul>${r.gaps.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}${r.bdd.length?`<details><summary>상황 → 행동 → 결과 예시 · 제안</summary>${r.bdd.map(x=>`<p>${esc(x.given)} → ${esc(x.when)} → ${esc(x.then)}</p>`).join('')}</details>`:''}${r.evidence.length?`<details><summary>확인 가능한 자료 원문</summary>${r.evidence.map(x=>`<blockquote><strong>${esc(guideSources.find(z=>z.id===x.sourceId)?.name||x.sourceId)}</strong><p>${esc(x.quote)}</p></blockquote>`).join('')}</details>`:''}<button id="guide-review" class="primary" ${r.draft.title&&r.draft.need?'':'disabled'}>등록 폼에서 검토하기 →</button><p class="help">AI 제안을 확인한 뒤 저장합니다. 기존 합의·검수 결과는 자동 변경하지 않습니다. 미정 사항은 남겨둘 수 있어요.</p>`:'<p class="muted">대화하면서 필요한 기능·이유·동작·완료 기준이 이곳에 정리됩니다.</p>'}</aside></div>`;
 layoutGuideDraft();
 enhanceGuide();if(r&&typeof showConnectionProposals==='function')showConnectionProposals(r);
 if($('#go-ai-setup'))$('#go-ai-setup').onclick=()=>{workspaceView='ai-setup';shell()};
 $('#guide-new').onclick=()=>startGuide();$('#guide-existing-start').onclick=()=>{const id=$('#guide-existing').value;if(id)startGuide(id);else toast('요건을 먼저 선택해 주세요.')};
 document.querySelectorAll('[data-session]').forEach(b=>b.onclick=()=>{guideSession=guideSessions.find(x=>x.id===b.dataset.session);drawGuide()});
 document.querySelectorAll('[data-choice]').forEach(b=>b.onclick=()=>{$('#guide-input').value=r.choices[+b.dataset.choice];$('#guide-input').focus()});
 document.querySelectorAll('[data-candidate]').forEach(b=>b.onclick=()=>{$('#guide-input').value='이 요건부터 함께 정리해 주세요: '+r.candidates[+b.dataset.candidate];$('#guide-input').focus()});
 $('#guide-source').onsubmit=saveGuideSource;$('#guide-chat').onsubmit=sendGuide;
 if($('#guide-review'))$('#guide-review').onclick=reviewGuide;
 const messages=$('#guide-messages');messages.scrollTop=messages.scrollHeight;
}
async function startGuide(requirementId=''){const epoch=guideEpoch;try{const session=await api(guidePath()+'sessions','POST',{requirementId});if(epoch!==guideEpoch)return;guideSession=session;guideSessions.push(session);drawGuide()}catch(e){if(epoch===guideEpoch)toast(e.message)}}
async function saveGuideSource(e){e.preventDefault();const epoch=guideEpoch,base=guidePath();const f=e.target,b=$('button',f),result=$('#source-result');b.disabled=true;
 try{const body=Object.fromEntries(new FormData(f));const file=$('#source-file').files[0];if(file){if(file.size>500000)throw Error('파일은 500KB 이하여야 합니다. 필요한 본문만 붙여 넣어도 됩니다.');if(body.text.trim())throw Error('파일과 붙여 넣기 중 하나만 사용해 주세요.');body.name=body.name||file.name;body.fileData=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('파일을 읽지 못했습니다.'));reader.readAsDataURL(file)});body.fileName=file.name;const saved=await api(base+'sources','POST',body);if(epoch!==guideEpoch)return;guideSources.push(saved)}else {const saved=await api(base+'sources','POST',body);if(epoch!==guideEpoch)return;guideSources.push(saved)}drawGuide();toast('자료를 프로젝트에 보관했어요. AI 분석은 대화를 보낼 때 실행됩니다.')}catch(error){result.textContent=error.message;b.disabled=false}}
async function sendGuide(e){
 e.preventDefault();const input=$('#guide-input'),message=input.value.trim();if(!message||guideSending)return;
 const epoch=guideEpoch,pid=selectedProject,form=e.target;
 guideSending=true;const controls=[...document.querySelectorAll('#content button,#content input,#content textarea,#content select')].map(el=>[el,el.disabled]);
 controls.forEach(([el])=>el.disabled=true);form.setAttribute('aria-busy','true');
 const status=$('#guide-error'),submit=$('button.primary',form),started=Date.now();
 status.className='guide-feedback pending';submit.textContent='AI가 정리 중…';
 const update=()=>{const sec=Math.floor((Date.now()-started)/1000);status.textContent=sec<25?`이번 답변의 변경사항을 확인하고 있어요 · ${sec}초`:`바뀐 내용과 다음 질문을 정리하고 있어요 · ${sec}초. 최대 3분 정도 걸릴 수 있어요.`};update();const timer=setInterval(update,1000);
 try{
  if(!guideSession){const created=await api('/projects/'+pid+'/guide/sessions','POST',{});if(epoch!==guideEpoch)return;guideSession=created;guideSessions.push(created)}
  const sid=guideSession.id,result=await api('/projects/'+pid+'/guide/sessions/'+sid,'POST',{message,version:guideSession.version});
  if(epoch!==guideEpoch)return;if(result.id!==sid){guideSessions=guideSessions.map(x=>x.id===sid?{...x,continuedTo:result.id,version:x.version+1}:x);guideSessions.push(result);toast('대화가 길어져 새 대화로 이어졌어요. 최신 초안과 마지막 답변을 이어받았습니다.')}else guideSessions=guideSessions.map(x=>x.id===sid?result:x);guideSession=result;drawGuide();
 }catch(error){if(epoch===guideEpoch){status.className='guide-feedback failed';status.textContent=error.message+' 입력한 답변은 남겨두었습니다. 내용을 확인한 뒤 다시 시도해 주세요.';submit.textContent='다시 시도하기 →'}}
 finally{clearInterval(timer);guideSending=false;form.removeAttribute('aria-busy');controls.forEach(([el,disabled])=>{if(el.isConnected)el.disabled=disabled})}
}
function reviewGuide(){const s=guideSession,r=s.result;const original=localReqs().find(x=>(x.source||'').includes('AI 작성 대화 '+(s.rootSessionId||s.id)))||s.baseRequirement||{};
 if(original.id&&requirements.find(x=>x.id===original.id)?.version!==original.version){toast('기존 요건이 변경되었습니다. 최신 요건으로 새 대화를 시작해 주세요.');return}
 const draft=original.id?Object.fromEntries(Object.entries(r.draft).filter(([,v])=>v.trim())):r.draft;
 const item={...original,...draft,projectId:selectedProject,source:[original.source,`AI 작성 대화 ${s.rootSessionId||s.id} / 현재 대화 ${s.id} / 자료 ${(s.sourceIds||[]).join(', ')}`].filter(Boolean).join('\n')};
 if(!original.id){item.status='수집';item.questions={exceptions:'모르겠어요',interfaces:'모르겠어요',policy:'모르겠어요'};item.scenarios=r.bdd.filter(x=>x.given&&x.when&&x.then).map((x,i)=>({...x,id:'SC-'+String(i+1).padStart(2,'0'),agreement:'제안',test:'미실시'}))}
 item.decisions=mergeGuideQuestions(original.decisions||[],r.gaps);
 item.nextAction=r.gaps[0]||original.nextAction||'담당자와 AI 제안 내용 확인';edit(typeof mergeConnectionProposals==='function'?mergeConnectionProposals(item,r):item);dirty=true;
}

const apiSetupScreen=aiSetup;
aiSetup=async function(){
 const epoch=guideEpoch;$('#content').innerHTML='<div class="loading">이 PC에 설치된 AI를 찾고 있어요…</div>';
 try{const s=await api('/ai/status');if(epoch!==guideEpoch)return;
 $('#content').innerHTML=`<div class="hero"><div><div class="eyebrow">LOCAL AI CONNECTION</div><h1>평소 쓰던 AI를 연결하세요</h1><p>각자의 PC에 로그인된 AI를 사용합니다. 팀 자료와 요건은 공통 작업실에 보관합니다.</p></div></div><div class="guide-setup"><section class="panel section formstack"><h2>1. 사용할 AI 선택</h2><p>공식 CLI가 설치되어 있어야 합니다. 아래에서 설치 여부를 확인할 수 있어요.</p><form id="local-ai-form" class="formstack">${(s.available||[]).map(a=>`<label class="info"><span><input type="radio" name="provider" value="${a.id}" ${a.installed?'':'disabled'} ${s.provider===a.id?'checked':''}> ${esc(a.name)}</span><span class="field-guide">${a.installed?'이 PC에서 발견했어요':'공식 CLI 설치가 필요해요'}</span></label>`).join('')}<h2>2. AI 계정 로그인</h2><div id="ai-account" class="info" role="status">계정 상태를 확인하고 있어요…</div><div class="row"><button type="button" id="ai-login">공식 로그인 창 열기</button><button type="button" id="ai-account-refresh">로그인 상태 다시 확인</button></div><p class="help">공식 브라우저에서 로그인한 뒤 상태를 다시 확인하세요. 이 PC의 선택한 AI 로그인에 적용됩니다. 작업실 계정은 유지됩니다.</p><h2>3. 사용할 모델</h2><label>모델 선택<select id="ai-model"><option value="">AI 기본 모델</option></select><span id="ai-model-note" class="field-guide"></span></label><label id="ai-custom-wrap" class="hidden">모델 ID 직접 입력<input id="ai-custom-model" maxlength="100" placeholder="사용 가능한 정확한 모델 ID"></label><h2>4. 연결 확인</h2><p>선택한 AI의 로그인 계정으로 짧은 안내를 요청합니다. 프로젝트 자료는 보내지 않으며 해당 계정의 사용량에 포함될 수 있습니다.</p><button class="primary">연결 시험하고 사용하기</button><div id="local-ai-result" role="status"></div></form></section><aside class="panel section formstack"><h2>처음 설치하나요?</h2><p>Codex 또는 Claude Code를 설치하고 본인 계정으로 로그인한 뒤 이 화면을 새로고침하세요. 데스크톱 앱만 설치한 경우 CLI가 별도로 필요할 수 있습니다.</p><a href="https://developers.openai.com/codex/cli/" target="_blank" rel="noopener">Codex 공식 설치 안내 ↗</a><a href="https://code.claude.com/docs/en/quickstart" target="_blank" rel="noopener">Claude Code 공식 설치 안내 ↗</a><div class="info">로컬 앱이지만 AI 처리는 선택한 서비스에서 이루어집니다. 인터넷 연결과 계정 사용 권한·한도가 필요합니다.</div><p>현재 선택: ${esc(s.provider==='codex'?'Codex':s.provider==='claude'?'Claude Code':s.configured?'OpenAI API':'아직 없음')}</p><p>최근 연결 시험: ${esc(s.testedAt||'아직 없음')}</p><button id="local-back">프로젝트로 돌아가기</button>${me.role==='admin'?'<details><summary>다른 연결 방식</summary><button id="open-api-setup">API 키로 연결</button></details>':''}</aside></div>`;
 const first=$('#local-ai-form input:not(:disabled)');if(first&&!$('#local-ai-form input:checked'))first.checked=true;
 let accountSequence=0;
 const refreshAccount=async()=>{
  const provider=$('#local-ai-form input:checked')?.value;if(!provider)return;
  const seq=++accountSequence;$('#ai-account').textContent='계정과 모델 목록을 확인하고 있어요…';
  $('#ai-model').innerHTML='<option value="">AI 기본 모델</option>';$('#ai-model').disabled=true;
  $('#ai-custom-wrap').classList.add('hidden');
  try{const info=await api('/ai/account/'+provider);if(epoch!==guideEpoch||seq!==accountSequence)return;
   $('#ai-account').textContent=(info.loggedIn?'로그인됨 · '+(info.account||'연결된 계정'):'아직 로그인되지 않았어요.')+(info.loginState==='running'?' · 공식 로그인 진행 중':info.loginState==='failed'?' · 로그인 미완료, 다시 시도하세요':'');
   const models=info.models||[];$('#ai-model').innerHTML='<option value="">AI 기본 모델</option>'+models.map(m=>`<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('')+'<option value="__custom">모델 ID 직접 입력</option>';
   const current=s.provider===provider?s.model:'';
   if(current){if(models.some(m=>m.id===current))$('#ai-model').value=current;else{$('#ai-model').value='__custom';$('#ai-custom-model').value=current;$('#ai-custom-wrap').classList.remove('hidden')}}
   $('#ai-model-note').textContent=info.modelNote;
  }catch(error){if(epoch===guideEpoch&&seq===accountSequence){$('#ai-account').textContent=error.message;$('#ai-model').innerHTML='<option value="">AI 기본 모델</option><option value="__custom">모델 ID 직접 입력</option>';$('#ai-model-note').textContent='목록을 읽지 못했습니다. 기본 모델 또는 알고 있는 모델 ID를 사용할 수 있습니다.'}}
  finally{if(epoch===guideEpoch&&seq===accountSequence)$('#ai-model').disabled=false}
 };
 document.querySelectorAll('#local-ai-form [name=provider]').forEach(x=>x.onchange=refreshAccount);
 $('#ai-model').onchange=()=>$('#ai-custom-wrap').classList.toggle('hidden',$('#ai-model').value!=='__custom');
 $('#ai-account-refresh').onclick=refreshAccount;
 $('#ai-login').onclick=async()=>{const provider=$('#local-ai-form input:checked')?.value;if(!provider)return;const button=$('#ai-login');button.disabled=true;try{await api('/ai/login','POST',{provider});if(epoch===guideEpoch)$('#ai-account').textContent='공식 브라우저에서 로그인하세요. 완료 후 로그인 상태 다시 확인을 눌러 주세요. 창이 열리지 않으면 해당 CLI에서 로그인한 뒤 다시 확인하세요.'}catch(error){if(epoch===guideEpoch)$('#ai-account').textContent=error.message}finally{button.disabled=false}};
 refreshAccount();

 $('#local-back').onclick=()=>{workspaceView='requirements';shell()};if($('#open-api-setup'))$('#open-api-setup').onclick=()=>apiSetupScreen();
 $('#local-ai-form').onsubmit=async e=>{e.preventDefault();const selected=$('#local-ai-form input:checked');if(!selected){$('#local-ai-result').textContent='사용할 AI를 설치하고 선택해 주세요.';return}const b=$('button.primary',e.target);b.disabled=true;$('#local-ai-result').textContent='AI에 연결하고 있어요. 최대 3분 정도 기다려 주세요…';try{await api('/ai/local-connect','POST',{provider:selected.value,model:$('#ai-model').value==='__custom'?$('#ai-custom-model').value.trim():$('#ai-model').value});if(epoch===guideEpoch)$('#local-ai-result').textContent='연결됐어요. 프로젝트에서 AI와 요건 만들기를 시작하세요.'}catch(error){if(epoch===guideEpoch)$('#local-ai-result').textContent=error.message}finally{b.disabled=false}};
 }catch(error){if(epoch===guideEpoch)$('#content').textContent=error.message}
};

// Escape before adding a deliberately small formatting subset; AI HTML is never executed.
let guideSending=false;
function guideText(text){return esc(text).replace(/\*\*([^*\n]+)\*\*/g,'<b>$1</b>')}
function mergeGuideQuestions(existing,gaps){
 const rows=existing.map(x=>({...x})),seen=new Set(rows.map(x=>x.question.trim()));
 for(const question of gaps){if(!question.trim()||seen.has(question.trim()))continue;
  if(rows.length>=100){toast('질문이 100개를 넘어 일부는 대화에 남아 있습니다. 기존 질문을 정리한 뒤 추가해 주세요.');break}
  let n=1;while(rows.some(x=>x.id==='D-'+String(n).padStart(2,'0')))n++;
  rows.push({id:'D-'+String(n).padStart(2,'0'),question,owner:'',due:'',status:'미정',answer:'',evidence:''});seen.add(question.trim());
 }return rows;
}
function enhanceGuide(){
 const r=guideSession?.result,card=$('.guide-draft'),body=$('.guide-draft-body'),layout=$('.guide-layout');
 layout.classList.add('guide-refined');
 if(guideSession?.continuedFrom){const note=document.createElement('p');note.className='help';note.textContent='긴 대화에서 이어왔어요. 최신 초안·미정 질문·최근 대화를 기준으로 작성하며, 이전 대화는 내 작성 대화에 보관됩니다.';$('.guide-conversation>.section').append(note)}
 if(guideSession?.continuedTo){const note=document.createElement('div');note.className='info';note.innerHTML='새 대화로 이어진 이전 이력입니다. <button type="button" id="open-continuation">이어진 대화 열기 →</button>';$('.guide-conversation>.section').append(note);$('#open-continuation').onclick=()=>{const next=guideSessions.find(x=>x.id===guideSession.continuedTo);if(next){guideSession=next;drawGuide()}else guideHome()};$('#guide-input').disabled=true;$('#guide-chat button.primary').disabled=true}

 const core=['title','need','flow','expected'],filled=core.filter(k=>r?.draft?.[k]?.trim()).length;
 const steps=document.createElement('ol');steps.className='guide-progress';steps.setAttribute('aria-label','요건 작성 순서');
 steps.innerHTML=['업무 이야기하기','요건 구체화하기','검토하고 등록하기'].map((label,i)=>`<li class="${i===(r?1:0)?'current':''}" ${i===(r?1:0)?'aria-current="step"':''}><span>0${i+1}</span>${label}</li>`).join('');
 const hero=$('.hero'),heroActions=document.createElement('div'),provider=hero.querySelector(':scope > .pill');
 heroActions.className='guide-hero-actions';heroActions.append(steps);if(provider)heroActions.append(provider);hero.append(heroActions);
 // Keep supporting material available without competing with the conversation.
 const side=$('.guide-side'),resources=document.createElement('details');resources.className='guide-resources';
 resources.innerHTML=`<summary>프로젝트 자료 <span class="pill">${guideSources.length}</span></summary>`;
 while(side.firstChild&&side.firstChild.tagName!=='HR')resources.append(side.firstChild);
 if(side.firstChild?.tagName==='HR')side.firstChild.remove();side.prepend(resources);
 const firstHeading=resources.querySelector('h2');if(firstHeading)firstHeading.remove();
 enableGuideReorder(side);
 const header=$('.guide-draft-header');
 const summary=document.createElement('div');summary.className='guide-checklist';
 summary.innerHTML=`<div class="row spread"><strong>기본 항목 ${filled}/4 작성</strong><span>내용 검토 전</span></div><div class="guide-checks">${core.map(k=>`<span class="${r?.draft?.[k]?.trim()?'filled':''}">${r?.draft?.[k]?.trim()?'✓':'○'} ${guideLabels[k]}</span>`).join('')}</div>`;header.append(summary);
 if(r){
  const fields=[...body.children].filter(el=>el.tagName==='DIV'&&el.querySelector('h3'));
  const extra=document.createElement('details');extra.className='guide-detail-group';extra.innerHTML='<summary>범위·예외·정책 자세히 보기</summary>';
  fields.forEach(el=>{if(!core.some(k=>guideLabels[k]===el.querySelector('h3').textContent))extra.append(el);else el.classList.add('guide-core-field')});
  if(extra.children.length>1)body.append(extra);
  const list=body.querySelector('ul');if(list){const heading=list.previousElementSibling,questions=document.createElement('details');questions.className='guide-detail-group guide-open-questions';questions.innerHTML=`<summary>더 확인할 질문 <span class="pill orange">${r.gaps.length}개</span></summary><p class="help">미정으로 등록해 담당자·기한을 정할 수 있어요.</p>`;list.before(questions);heading?.remove();questions.append(list)}
  if(!filled)card.classList.add('is-empty');
 }else{body.innerHTML='<div class="guide-empty-mark">✧</div><h3>한 문장이면 시작할 수 있어요</h3><p class="muted">누가, 어떤 업무에서 불편한지만 알려주세요. 필요한 이유와 완료 기준은 대화하며 함께 정리해요.</p><div class="guide-empty-sample"><small>이렇게 정리돼요 · 예시</small><strong>고객이 주문 취소 상태를 확인한다</strong><p>주문 상세에서 취소 상태와 환불 예정일을 보여준다.</p></div>'}
 const input=$('#guide-input');input.setAttribute('aria-describedby','guide-input-help');
 const helper=document.createElement('span');helper.id='guide-input-help';helper.className='field-guide';helper.textContent='예: 배송 전에는 취소할 수 있고, 배송 후 처리는 아직 정하지 못했어요.';input.after(helper);
 if(!guideSession?.messages.length){const examples=document.createElement('div');examples.className='guide-starters';examples.innerHTML='<small>어디서 시작할지 막막하다면</small>'+['자료에서 요건 후보를 찾아주세요','고객이 주문 취소 상태를 확인하고 싶어요','기존 업무의 불편한 점부터 정리하고 싶어요'].map(x=>`<button type="button">${x} ↗</button>`).join('');$('#guide-messages').append(examples);examples.querySelectorAll('button').forEach(b=>b.onclick=()=>{input.value=b.textContent.replace(' ↗','');input.focus()})}
 const review=$('#guide-review');if(review){review.textContent='등록 폼에서 검토하기 →';review.nextElementSibling.textContent=`미정 질문 ${r.gaps.length}개도 함께 전달합니다. 내용을 검토하고 저장해야 팀에 등록돼요.`}
}
