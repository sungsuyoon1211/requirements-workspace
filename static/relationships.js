'use strict';
// The same project-local data name is a shared business entity, never a sample value.
const dataKey=value=>String(value||'').trim().replace(/\s+/g,' ').toLocaleLowerCase();
defs.relations={title:'요건 연결',prefix:'REL',fields:[]};
defs.dataUses={title:'데이터 사용',prefix:'DATA',fields:[]};
const connectionRepeatCard=repeatCard;
repeatCard=function(kind,row){
 if(!['relations','dataUses'].includes(kind))return connectionRepeatCard(kind,row);
 const status=select('검토 상태','status',['제안','확인'],row.status||'제안');
 let fields;
 if(kind==='relations'){
  const options=[{value:'',label:'연결할 요건 선택'},...localReqs().filter(r=>r.id!==active.id).map(r=>({value:r.id,label:r.title+' · '+r.id}))];
  if(row.requirementId&&!options.some(x=>x.value===row.requirementId))options.push({value:row.requirementId,label:'확인할 수 없는 요건 · '+row.requirementId});
  fields=select('연결할 요건','requirementId',options,row.requirementId||'')+select('현재 요건과의 관계','type',['선행 필요','관련'],row.type||'선행 필요')+area('연결 이유','reason',row.reason||'')+status+`<input type="hidden" name="targetVersion" value="${Number(row.targetVersion)||0}">`;
 }else fields=`<label>데이터 이름<input name="name" list="project-data-names" maxlength="200" value="${esc(row.name||'')}" placeholder="예: 회원, 주문, 결제"><span class="field-guide">같은 데이터는 목록에서 같은 이름을 선택하세요. 실제 고객 정보는 입력하지 마세요.</span></label>`+select('이 요건에서 하는 일','operation',['생성','조회','변경','삭제'],row.operation||'조회')+area('사용 내용','description',row.description||'')+status;
 return `<div class="repeat-card" data-kind="${kind}"><div class="row spread"><strong>${defs[kind].title}</strong><button type="button" class="quiet" data-remove>항목 삭제</button></div><div class="grid2">${fields}</div></div>`;
};
const connectionEditorValues=editorValues;
editorValues=function(){const item=connectionEditorValues();item.relations=(item.relations||[]).map(r=>({...r,targetVersion:Number(r.targetVersion)||0}));return item};

function impactFor(item,all){
 const peers=all.filter(r=>r.projectId===item.projectId&&r.id!==item.id),found=new Map();
 const add=(r,reason)=>{if(!found.has(r.id))found.set(r.id,{id:r.id,title:r.title,reasons:[]});if(!found.get(r.id).reasons.includes(reason))found.get(r.id).reasons.push(reason)};
 const mine=new Set((item.dataUses||[]).filter(d=>d.status==='확인').map(d=>dataKey(d.name)));
 const systems=new Set((item.interfaces||[]).map(i=>dataKey(i.target)).filter(Boolean));
 for(const r of peers){
  for(const link of item.relations||[])if(link.status==='확인'&&link.requirementId===r.id)add(r,link.type==='선행 필요'?'현재 요건의 선행 요건':'직접 연결된 요건');
  for(const link of r.relations||[])if(link.status==='확인'&&link.requirementId===item.id)add(r,link.type==='선행 필요'?'현재 요건을 필요로 하는 후속 요건':'이 요건을 관련 요건으로 연결함');
  const shared=[...new Set((r.dataUses||[]).filter(d=>d.status==='확인'&&mine.has(dataKey(d.name))).map(d=>d.name))];
  if(shared.length)add(r,'같은 데이터 사용: '+shared.join(', '));
  const targets=[...new Set((r.interfaces||[]).filter(i=>systems.has(dataKey(i.target))).map(i=>i.target))];if(targets.length)add(r,'같은 연동 대상: '+targets.join(', '));
 }
 // Propagate only along confirmed prerequisite edges; cycles are guarded in both layers.
 const queue=[...found.keys(),...(item.id?[item.id]:[])],visited=new Set(queue);
 for(let i=0;i<queue.length;i++)for(const r of peers)if((r.relations||[]).some(e=>e.status==='확인'&&e.type==='선행 필요'&&e.requirementId===queue[i])&&!visited.has(r.id)){
  visited.add(r.id);queue.push(r.id);add(r,'연결된 요건의 후속 요건 · 간접 영향 후보');
 }
 return [...found.values()];
}
function connectionImpactHtml(item){
 const impacts=impactFor(item,requirements),changed=(item.relations||[]).filter(e=>e.targetVersion&&requirements.some(r=>r.id===e.requirementId&&r.version>e.targetVersion));
 return `${changed.length?`<div class="hint-banner"><strong>연결한 뒤 내용이 바뀐 요건 ${changed.length}개</strong>${changed.map(e=>{const r=requirements.find(x=>x.id===e.requirementId);return `<p>${esc(r.title)} · 확인 기준 v${e.targetVersion} → 현재 v${r.version}</p>`}).join('')}<p>변경 내용을 확인한 뒤 해당 연결을 삭제하고 다시 추가하면 새 버전을 기준으로 저장합니다.</p></div>`:''}<p class="help">확인된 연결과 동일한 데이터·시스템 이름으로 찾은 검토 후보입니다. 실제 영향의 크기·발생 여부를 보장하지 않습니다. 목록은 작업실에서 불러온 최신 기록 기준입니다.</p>${impacts.length?impacts.map(x=>`<article class="impact-item"><strong>${esc(x.title)}</strong><small>${esc(x.id)}</small><ul>${x.reasons.map(reason=>`<li>${esc(reason)}</li>`).join('')}</ul></article>`).join(''):'<p class="muted">현재 기록으로 연결되는 요건이 없습니다. 연결 누락이 없는지 함께 확인하세요.</p>'}`;
}
const connectionEdit=edit;
edit=function(item={}){
 connectionEdit(item);const form=$('#workspace-form');if(!form)return;
 const names=[...new Set(localReqs().flatMap(r=>(r.dataUses||[]).map(d=>d.name)))];
 const section=document.createElement('details');section.id='connections-panel';
 section.innerHTML=`<summary>연결된 요건·데이터와 변경 영향 <span class="muted">AI 제안을 확인하고 저장해요</span></summary><div class="section formstack"><div class="info">예: 회원가입은 회원 데이터를 생성하고, 로그인은 같은 회원 데이터를 조회합니다. 필요한 관계만 추가하세요. 제안은 확인으로 바꿔야 영향도에 반영됩니다.</div><h3>어떤 요건과 연결되나요?</h3><p class="help">선행 필요: 현재 요건이 선택한 요건을 필요로 합니다. 관련: 함께 검토할 관계입니다.</p>${structuredRows('relations',item.relations)}<h3>어떤 데이터를 사용하나요?</h3><datalist id="project-data-names">${names.map(n=>`<option value="${esc(n)}">`).join('')}</datalist>${structuredRows('dataUses',item.dataUses)}<h3>변경할 때 함께 검토할 요건</h3><div id="connection-impact"></div><button type="button" id="refresh-impact">현재 입력으로 영향 확인</button></div>`;
 $('#ws-ready').before(section);
 const render=()=>{$('#connection-impact').innerHTML=connectionImpactHtml(editorValues())};render();$('#refresh-impact').onclick=render;
 form.addEventListener('change',e=>{if(e.target.name==='requirementId'){const stamp=e.target.closest('.repeat-card').querySelector('[name=targetVersion]');stamp.value='0'}if(e.target.closest('#connections-panel'))render()});
 form.addEventListener('click',e=>{if(e.target.closest('[data-remove]'))queueMicrotask(()=>{if(form.isConnected)render()})});
 if(item._connectionProposalCount){section.open=true;const note=document.createElement('div');note.className='section info';note.textContent=`AI가 요건·데이터·연동 ${item._connectionProposalCount}개를 제안했어요. 저장 전에 연결 대상과 사용 내용을 검토하세요.`;form.querySelector('.dialog-body').prepend(note)}
};

function mergeConnectionProposals(item,result){
 const relations=(item.relations||[]).map(x=>({...x})),dataUses=(item.dataUses||[]).map(x=>({...x})),interfaces=(item.interfaces||[]).map(x=>({...x}));let count=0;
 for(const row of result.relations||[])if(row.requirementId!==item.id&&!relations.some(x=>x.requirementId===row.requirementId&&x.type===row.type)){relations.push({...row,status:'제안',targetVersion:0});count++}
 for(const row of result.dataUses||[])if(!dataUses.some(x=>dataKey(x.name)===dataKey(row.name)&&x.operation===row.operation)){dataUses.push({...row,status:'제안'});count++}
 for(const row of result.interfaces||[])if(!interfaces.some(x=>dataKey(x.target)===dataKey(row.target)&&dataKey(x.timing)===dataKey(row.timing)&&dataKey(x.direction)===dataKey(row.direction))){let n=1;while(interfaces.some(x=>x.id==='IF-'+String(n).padStart(2,'0')))n++;interfaces.push({...row,id:'IF-'+String(n).padStart(2,'0')});count++}
 return {...item,relations,dataUses,interfaces,_connectionProposalCount:count,questions:{...item.questions,...(interfaces.length?{interfaces:'있어요'}:{})}};
}
function showConnectionProposals(result){
 const rows=[...(result.relations||[]).map(x=>`요건 · ${requirements.find(r=>r.id===x.requirementId)?.title||x.requirementId} (${x.type}) — ${x.reason}`),...(result.dataUses||[]).map(x=>`데이터 · ${x.name} / ${x.operation} — ${x.description}`),...(result.interfaces||[]).map(x=>`연동 · ${x.target} — ${x.direction}`)];
 if(!rows.length)return;const detail=document.createElement('details');detail.className='guide-detail-group';detail.innerHTML=`<summary>요건·데이터·연동 제안 <span class="pill">${rows.length}개</span></summary><p class="help">등록 폼에서 연결 정보를 확인하고 수정할 수 있어요.</p><ul>${rows.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;$('.guide-draft-body')?.append(detail);
}
const connectionShell=shell;
shell=function(){connectionShell();if(!projectNow())return;const button=document.createElement('button');button.textContent='↔ 연결·영향 보기';button.className=workspaceView==='connections'?'active':'';button.onclick=()=>{workspaceView='connections';shell()};$('.nav')?.append(button);if(workspaceView==='connections')connectionHome()};
function connectionHome(){
 const rows=localReqs();$('#content').innerHTML=`<div class="hero"><div><div class="eyebrow">CONNECTIONS</div><h1>변경 전에, 연결된 요건을 확인하세요</h1><p>요건의 선행 관계와 같은 데이터·연동을 사용하는 요건을 함께 살펴봅니다.</p></div></div><section class="panel section formstack"><label>변경하거나 검토할 요건<select id="impact-requirement"><option value="">요건 선택</option>${rows.map(r=>`<option value="${r.id}">${esc(r.title)}</option>`).join('')}</select></label><div id="impact-result"><p class="muted">요건을 선택하면 직접 연결과 간접 영향 후보를 표시합니다.</p></div></section>`;
 $('#impact-requirement').onchange=e=>{const item=rows.find(r=>r.id===e.target.value);$('#impact-result').innerHTML=item?`<div class="row spread"><h2>${esc(item.title)}</h2><button id="edit-connections">연결 정보 검토</button></div>${connectionImpactHtml(item)}`:'요건을 선택하세요.';if(item)$('#edit-connections').onclick=()=>edit(item)};
}
