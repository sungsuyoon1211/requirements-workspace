"""Interview depth changes, while approval and evidence rules stay invariant."""
DEFAULT = 'MIDIUN'
PROFILES = {
    'ROW': {
        'focus': '핵심 정의',
        'criteria': '사용자와 상황, 필요한 이유, 핵심 행동, 관찰 가능한 완료 기준을 쉬운 말로 확인한다. 정상 흐름 예시 하나를 먼저 정리한다.',
        'depth': '한 번에 가장 쉬운 핵심 질문 하나와 선택지 2~3개. 기본 내용이 있으면 검토를 제안한다. 상세 상태표·연동 명세·BDD 작성을 일괄 요구하지 않는다.',
    },
    'MIDIUN': {
        'focus': '표준 정의',
        'criteria': 'ROW 기준에 더해 시작 조건, 기본 업무 흐름, 포함·제외 범위, 대표 예외, 권한·정책·연동의 필요 여부를 확인한다. 정상·대표 예외의 완료 확인 예시를 정리한다.',
        'depth': '한 번에 질문 하나. 예외·연동·정책이 있다고 답한 항목만 구체화하고 없거나 모르는 항목에 불필요한 세부 질문을 반복하지 않는다.',
    },
    'HARD': {
        'focus': '상세 정의',
        'criteria': 'MIDIUN 기준에 더해 역할별 권한, 상태 전이·승인 책임, 데이터 생성·조회·변경·삭제, 연동의 대상·방향·시점·실패·대체 절차, 경계값·실패·중복 시나리오, 측정 가능한 품질·검수 기준을 해당할 때 확인한다.',
        'depth': '한 번에 질문 하나로 조건과 결과를 깊게 추적한다. 정상·예외·경계의 Given/When/Then을 구체적으로 제안하되 숫자·담당자·합의는 근거 없으면 미정으로 둔다.',
    },
    'VERYHARD': {
        'focus': '심층 정의',
        'criteria': 'HARD 기준에 더해 동시 처리·재시도·멱등성·부분 실패·복구·정합성, 접근 통제·감사, 부하·가용성·관측, 이관·전환·롤백, 요건 간 의존성과 변경 영향·출처 추적을 실제 위험에 해당할 때 확인한다.',
        'depth': '한 번에 질문 하나. 위험도가 높은 미정 사항부터 원인·조건·관찰 결과·복구·검증 근거를 추적한다. 무관한 보안·법규·인프라 요구를 자동 추가하거나 범위를 확대하지 않는다.',
    },
}

def validate(value, Problem):
    if not isinstance(value, str) or value not in PROFILES:
        raise Problem('요건 정의 레벨은 ROW, MIDIUN, HARD, VERYHARD 중에서 선택해 주세요.')
    return value

def instructions(level):
    profile = PROFILES[level]
    return (f'요건 정의 레벨: {level} · {profile["focus"]}\n'
            f'확인 기준: {profile["criteria"]}\n질문 깊이: {profile["depth"]}\n'
            '레벨은 질문의 디테일과 깊이를 정하며 요건 확정·검수 규칙을 완화하지 않는다. '
            '모든 레벨에서 근거 없는 수치·정책·합의를 만들지 않고 중요한 미정 위험은 드러낸다. '
            '레벨을 낮춰도 기존 초안·예외·합의·미정 질문을 삭제하지 않는다. '
            '레벨을 높이면 이미 확인한 답은 재사용하고 추가로 필요한 질문만 한다. '
            '지정 기준에서 적용 가능한 내용이 정리되면 등록 폼 검토로 안내한다.')
