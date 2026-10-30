'use strict';
// Persistent field guidance and a readiness checklist share the server's sign-off rules.
const writingHelp={
title:'누가 무엇을 할 수 있어야 하는지 적으세요. 예: 고객은 주문 상세에서 취소 상태를 확인할 수 있다.',
need:'현재 문제와 필요한 이유를 적으세요. 예: 취소 여부를 몰라 고객센터 문의가 반복된다.',
owner:'내용을 정리하고 다음 확인을 진행할 담당자입니다. 아직 정하지 못했다면 나를 선택하세요.',
project:'함께 관리할 업무나 프로젝트 이름입니다. 예: 주문 서비스 개편. 확정 전에는 분류 전을 실제 이름으로 바꾸세요.',
nextAction:'다음에 할 구체적인 행동을 적으세요. 예: 운영팀과 취소 가능한 주문 상태 확인.',
due:'개발 완료일이 아닌 다음 확인의 기한입니다. 예: 다음 고객 회의 전날.',
priority:'Must: 없으면 업무 불가 / Should: 우회 가능하지만 비효율 / Could: 편의 개선 / Won’t: 이번 제외. 기본값 Should는 확인 후 조정하세요.',
status:'수집: 요청 접수 / 검토: 내용 보완 / 확정: 합의 완료 / 진행: 구현 중 / 완료: 검수 통과 / 보류: 잠시 중단. 확정 이후는 관리자가 처리합니다.',
story:'누가·어떤 상황에서·무엇을·왜 원하는지 적으세요. 예: 고객은 취소를 신청한 뒤 환불 진행 상태를 확인하고 싶다.',
flow:'앞뒤 업무까지 연결하세요. 예: 주문 조회 → 취소 신청 → 운영 검토 → 환불 요청 → 결과 안내.',
scope:'이번에 만드는 기능의 범위입니다. 예: 전체 주문 취소와 처리 상태 조회.',
excluded:'이번에 하지 않을 일과 이유입니다. 예: 부분 취소는 정산 정책 미정으로 다음 단계. 제외가 없으면 ‘제외 없음’으로 작성하세요.',
source:'합의의 출처를 찾을 수 있게 남기세요. 예: 고객 회의록 10/16, 안건 3, 공유 문서 경로.',
cta:'사용자의 주요 행동과 가능한 조건입니다. 예: 배송 전 주문에만 취소 요청 버튼을 표시한다.',
design:'화면 설계의 링크나 문서 경로입니다. 예: 주문 상세 화면 설계 v2, 4페이지.',
object:'상태와 데이터를 관리하는 업무 단위입니다. 예: 주문 한 건 또는 취소 신청 한 건.',
states:'상태·조건·변경 주체를 함께 적으세요. 예: 접수 → 운영자 승인 → 환불 중 → 완료. 배송 시작 후에는 취소 불가.',
dataFlow:'누가 만들고 어디서 바꾸며 누가 사용하는지 적으세요. 예: 고객이 신청 → 운영자가 사유 검토 → 정산팀이 환불 처리에 사용.',
responsibility:'할 수 있는 권한과 문제 발생 시 책임을 구분하세요. 예: 운영자는 승인 가능, 오승인 책임은 운영팀장.',
approvalFlow:'승인 순서와 부재·반려 처리를 적으세요. 예: 담당자 검토 → 팀장 승인, 부재 시 대리 승인, 반려 시 신청자에게 반환.',
exceptions:'실패·취소·반려 후 어디로 돌아가는지 적으세요. 예: 환불 실패 시 승인 상태 유지 → 원인 확인 → 같은 건으로 재시도.',
migration:'연동과 별개로 기존 자료를 옮기는 작업입니다. 예: 전환일 이전 미처리 신청만 이관, 운영팀 대사 후 승인. 이관이 없으면 이유를 적으세요.',
risk:'일정이나 범위에 영향을 주는 조건입니다. 예: 외부 결제사 테스트 계정 발급 지연.',
successMetric:'업무 효과의 숫자와 측정 기간입니다. 예: 오픈 후 4주 동안 취소 상태 문의를 기존 대비 20% 줄인다. 수치는 고객 합의 후 확정하세요.',
changeReason:'확정한 내용을 왜 바꾸는지 적으세요. 예: 고객이 배송 전 취소 허용 범위를 변경 요청.',
changeImpact:'연관 요건·화면·데이터 영향을 적으세요. 예: 주문 상세, 결제사 환불 호출, 운영 매뉴얼 변경.',
changeApprover:'변경을 실제 승인한 주체와 승인 근거를 남기세요. 예: 고객 운영팀장, 변경 회의록 안건 2.',
id:'자동 부여한 번호로 다른 항목과 연결합니다. 수정한다면 중복 없이 입력하세요.',
rule:'이 예시가 검증할 규칙입니다. 예: AC-1 배송 전 주문의 전체 취소 허용.',
given:'행동 전 이미 충족된 조건입니다. 예: 로그인한 고객의 결제 완료·배송 전 주문이다.',
when:'확인할 행동 하나를 적으세요. 예: 고객이 취소 요청 버튼을 누른다.',
then:'관찰 가능한 결과를 적으세요. 예: 상태가 취소 접수로 바뀌고 접수 번호가 표시된다.',
decision:'미정 정책의 질문 ID를 연결합니다. 예: D-01. 연결한 질문이 미정이면 합의보류·검수 보류로 저장하세요.',
agreement:'제안은 검토 전, 합의는 고객·기획·개발·QA가 결과에 동의한 상태입니다. 미정 정책이 있으면 합의보류.',
test:'미실시 → 실제 시험 후 통과 또는 실패. 정책 미정이면 보류. 통과·실패에는 아래 증빙이 필요합니다.',
actual:'예상 결과를 복사하지 말고 실제 관찰한 결과를 적으세요. 예: 접수 번호 C-102가 표시됐지만 상태가 바뀌지 않았다.',
tester:'실제 시험한 사람입니다. 예: QA 담당 김민수.',
testedAt:'실제로 시험한 날짜를 선택하세요. 아직 시험하지 않았다면 비워 두세요.',
evidence:'근거를 다시 열어 볼 수 있는 경로·링크를 적으세요. 예: 공유폴더/검수/SC-01.png 또는 합의 회의록 안건 번호.',
question:'결정이 필요한 질문을 한 가지씩 적으세요. 예: 결제사 조회 실패 시 취소 접수를 허용할까요?',
answer:'누가 언제 어떤 조건으로 결정했는지 적으세요. 예: 운영팀이 10/16 회의에서 조회 재시도 후 접수하도록 결정.',
target:'연결할 시스템 이름입니다. 예: 결제사 환불 API.',
direction:'요청과 응답 방향입니다. 예: 주문 시스템 → 결제사, 결제사 → 주문 시스템.',
timing:'언제 얼마나 자주 연결하는지 적으세요. 예: 운영자가 취소 승인할 때 건별 1회.',
data:'필수 입력과 결과를 적으세요. 예: 거래 번호·환불 금액 → 처리 번호·성공/실패 코드.',
failure:'실패 시 상태와 후속 행동입니다. 예: 완료로 표시하지 않고 재시도 안내, 기존 상태 유지.',
fallback:'연결이 복구되지 않을 때 대체 절차입니다. 예: 운영자가 결제사 포털에서 확인 후 처리 번호 입력. 대체가 없으면 이유 명시.',
what:'측정할 대상을 정하세요. 예: 취소 상태 조회 응답 시간.',
who:'누구 관점의 측정인지 적으세요. 예: 최종 사용자 브라우저 기준.',
where:'측정 환경과 범위를 적으세요. 예: 사내 테스트망, 브라우저에서 서버 왕복 포함.',
verify:'실제로 합격 여부를 확인할 방법입니다. 예: 동시 100명 조건에서 1,000회 조회 후 지연 분포 확인.'
};
const originalCollect=collect;
collect=function(){const r=originalCollect();r.applicability={};for(const key of ['interfaces','nfr'])r.applicability[key]={status:document.querySelector(`[name="apply_${key}"]`)?.value||'미정',reason:document.querySelector(`[name="reason_${key}"]`)?.value||''};return r;};
function draftForCheck(){const form=$('#req-form');return form?{...active,...collect()}:{...active,...Object.fromEntries(new FormData($('#easy-form')))};}
let checkTimer,checkSequence=0;
function scheduleCheck(){clearTimeout(checkTimer);checkTimer=setTimeout(checkNow,250);}
async function checkNow(){
 const holder=$('#completion-guide');if(!holder)return;const seq=++checkSequence;
 try{const result=await api('/check','POST',draftForCheck());if(seq!==checkSequence||!holder.isConnected)return;
 const gaps=result.gaps;
 holder.innerHTML=`<div class="row spread"><strong>${result.ready?'확정 준비 완료':'접수와 정의 완료는 달라요'}</strong><span class="pill">${gaps.length?($('#easy-form')?'요청 접수 단계':gaps.length+'개 보완 필요'):'필수 항목 작성됨'}</span></div><p>${gaps.length?'지금 저장해도 괜찮아요. 확정 전까지 아래 내용을 하나씩 보완하세요.':'필수 정보가 갖춰졌어요. 관리자가 실제 내용과 고객 합의를 검토한 뒤 확정하세요.'}</p>${gaps.length?`<div class="next-guide"><span>다음 단계 · ${esc(gaps[0].label)}</span><button type="button" data-jump="${esc(gaps[0].target)}">작성하러 가기 →</button></div><details><summary>나머지 확인 항목 보기</summary><ul>${gaps.slice(1).map(g=>`<li><span>${esc(g.label)}</span><button type="button" data-jump="${esc(g.target)}">이동</button></li>`).join('')}</ul></details>`:''}`;
 }catch(e){holder.textContent='보완 항목을 불러오지 못했어요. '+e.message;}
}
function jumpTo(target){
 if($('#easy-form')){const draft=draftForCheck(),wasDirty=dirty;advancedEdit(draft);dirty=wasDirty;addSimpleBack();}
 let el=$(`[name="${target}"]`,$('#req-form'))||$('#repeat-'+target)|| (target==='checks'?$('.checkrow'):null);
 if(!el)return;let parent=el.parentElement;while(parent){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement;}
 el.scrollIntoView({block:'center',behavior:'smooth'});const focus=el.matches('input,select,textarea,button')?el:el.querySelector('input,select,textarea,button')||el.parentElement.querySelector('[data-add]');focus?.focus({preventScroll:true});
}
function decorateGuide(){
 const form=$('#req-form')||$('#easy-form');if(!form)return;
 if(!$('#completion-guide')){const box=document.createElement('section');box.id='completion-guide';box.className='completion-guide';if(form.id==='easy-form')$('.section',form).insertAdjacentElement('afterend',box);else $('.dialog-body',form).prepend(box);box.addEventListener('click',e=>{const b=e.target.closest('[data-jump]');if(b)jumpTo(b.dataset.jump)});}
 if(form.id==='req-form')for(const key of ['interfaces','nfr']){const root=$('#repeat-'+key);if(!root||$(`[name="apply_${key}"]`,form))continue;const a=active.applicability?.[key]||{};root.insertAdjacentHTML('beforebegin',`<div class="applicability grid2">${select(key==='interfaces'?'다른 시스템과 연결하나요?':'별도로 확인할 품질 기준이 있나요?','apply_'+key,['미정','필요','해당없음'],a.status||'미정')}${field('해당 없으면 이유를 적어 주세요','reason_'+key,a.reason||'')}<p class="help full">${key==='interfaces'?'예: 단독 화면 안내 기능으로 외부 시스템과 데이터를 주고받지 않는다.':'성능뿐 아니라 보안·운영·사용성도 검토하세요. 예: 공통 품질 기준 NFR-공통-01로 관리하여 이 요건의 별도 기준은 없음.'} ‘필요’를 선택하면 아래 항목을 추가해 작성하세요.</p></div>`);}
 for(const el of form.querySelectorAll('input,select,textarea')){
  if(el.dataset.guided)continue;el.dataset.guided='1';const name=el.name,kind=el.closest('[data-kind]')?.dataset.kind;let guide=writingHelp[name];
  if(kind==='nfr'&&name==='when')guide='측정할 시간과 부하 조건입니다. 예: 업무 피크 시간대, 동시 사용자 100명.';
  if(kind==='nfr'&&name==='target')guide='숫자와 허용 범위를 적으세요. 예: 응답의 95%가 3초 이내, 최대 5초. 고객과 목표를 합의하세요.';
  if(kind==='decisions'&&name==='owner')guide='정책을 결정할 책임자입니다. 예: 고객 운영팀장. 요건 작성 담당자와 다를 수 있어요.';
  if(kind==='decisions'&&name==='due')guide='답변을 받기로 합의한 날짜입니다. 질문은 담당자와 기한을 함께 기록하세요.';
  if(kind==='decisions'&&name==='status')guide='미정: 답변 대기 / 결정: 답변과 근거를 기록한 상태. 결정 시 답변과 근거가 필수입니다.';
  if(kind==='interfaces'&&name==='owner')guide='연결 장애와 데이터 오류를 확인할 담당자입니다. 예: 결제 연동 담당자.';
  if(el.dataset.evidence)guide='정의한 내용을 찾을 수 있는 근거 또는 해당 없는 이유를 적으세요. 단순히 ‘없음’보다 업무상 이유를 설명하세요.';
  if(el.dataset.check)guide='정의: 구체적인 규칙을 작성함 / 해당없음: 적용하지 않는 이유를 기록함 / 미정: 아직 확인 필요.';
  if(!guide)continue;const note=document.createElement('span');note.className='field-guide';note.id='guide-'+(++decorateGuide.count);note.textContent=guide;el.setAttribute('aria-describedby',note.id);if(el.closest('.checkrow'))el.closest('.checkrow').append(note);else el.insertAdjacentElement('afterend',note);
 }
 if(!form.dataset.guideEvents){form.dataset.guideEvents='1';form.addEventListener('input',scheduleCheck);form.addEventListener('change',scheduleCheck);form.addEventListener('click',e=>{if(e.target.closest('[data-add],[data-remove]')){decorateGuide();scheduleCheck();}});}
 scheduleCheck();
}
decorateGuide.count=0;
const easyBase=edit,advancedBase=advancedEdit,shellBase=shell;
edit=function(item={}){easyBase(item);decorateGuide();};
advancedEdit=function(item={}){advancedBase(item);decorateGuide();};
shell=function(){shellBase();const toolbar=$('.toolbar');if(toolbar){const b=document.createElement('button');b.type='button';b.className='quiet';b.textContent='작성 예시 보기';b.onclick=()=>edit(example());toolbar.append(b);}};
