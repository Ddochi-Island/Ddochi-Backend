# 코드 테이블 (CODE/LABEL 마스터)

한글 자유 텍스트를 CHECK 제약으로 검증하던 컬럼들을, 영어 코드값 + FK로 바꾸면서
생긴 마스터 테이블들의 목록. 새로 코드 테이블을 추가할 때는 이 문서도 같이 갱신할 것.

## 패턴

- `XXX_CODES(코드 PK, LABEL, SORT_ORDER)` — 대분류. `LABEL`은 화면에 보여줄 한글.
- 소분류가 있으면 `XXX_SUB_REASON_CODES(코드 FK, SUB_CODE, LABEL, SORT_ORDER)` —
  복합키 `(코드, SUB_CODE)`라서 같은 소분류 이름(예: "환경")도 대분류별로 독립적으로 존재 가능.
- 실제 데이터 테이블(`TM_LOGS`, `SARANG_MATCH_HISTORIES` 등)의 컬럼은 코드값만 저장하고
  FK로 무결성 검증 — 표시할 땐 코드 테이블과 JOIN해서 LABEL을 가져옴.
- 프론트(Vue) → 백엔드로는 여전히 한글 문자열이 오는 경우가 많음(레거시 프론트를 그대로
  써서) — 백엔드가 `한글 → 코드` 역매핑 딕셔너리를 직접 들고 있다가 저장 시 변환함
  (`api/views/assets.py`의 `TM_RESULT`, `_RESULT_SUB_REASON_MAP` 등). 코드 테이블 자체를
  역조회하지 않음 — 코드 테이블은 어디까지나 "저장된 코드 → 표시용 LABEL" 정방향 전용.

## TM_RESULT_CODES / TM_SUB_REASON_CODES

`sql/10_tm_result_codes.sql`. `TM_LOGS.RESULT`/`TM_LOGS.SUB_REASON`이 참조.

| RESULT_CODE | LABEL | 비고 |
|---|---|---|
| `NO_ANSWER` | 부재중 | |
| `RESERVED_TM` | 예약 티엠 | |
| `MEET_FIX` | 만남 픽스 | STAGE를 `만픽`으로 전환시키는 트리거 |
| `UNFIT` | 비합 | |
| `REJECT` | 거절 | |
| `INVALID` | 무효 | |

`TM_SUB_REASON_CODES` — `UNFIT`/`REJECT`/`INVALID`에만 존재:

| RESULT_CODE | SUB_CODE | LABEL |
|---|---|---|
| UNFIT | `ENV_UNFIT` | 환경비합 |
| UNFIT | `DISTANCE_UNFIT` | 거리비합 |
| UNFIT | `AGE_UNFIT` | 나이비합 |
| UNFIT | `PERSONALITY_UNFIT` | 인성비합 |
| UNFIT | `MENTAL_HEALTH` | 정신질환 |
| UNFIT | `DUPLICATE` | 중복섭외 |
| REJECT | `N_REJECT` | N번 안받음 |
| REJECT | `OPT_OUT` | 수신거절 |
| REJECT | `SUSPICIOUS` | 의심/경계 |
| REJECT | `DISTANCE_BURDEN` | 거리부담 |
| REJECT | `FACE_TO_FACE_BURDEN` | 대면부담 |
| REJECT | `NO_BENEFIT` | 메리트부족 |
| INVALID | `DUPLICATE_APPLY` | 중복신청 |
| INVALID | `PRANK` | 장난/비방 |
| INVALID | `NOT_SELF` | 본인아님 |

## MATCH_RESULT_CODES / MATCH_SUB_REASON_CODES

`sql/11_match_result_codes.sql`. `SARANG_MATCH_HISTORIES.RESULT`/`SARANG_MATCH_HISTORIES.SUB_REASON`이 참조.
매칭 절대 지켜!(`MatchingScreen.vue`)의 결과입력 6옵션 + 밀림/2차만남에 대응.

| RESULT_CODE | LABEL | 비고 |
|---|---|---|
| `CANCEL` | 취소 | |
| `DELAY` | 밀림 | postpone-meeting에서 씀(아직 미구현) |
| `UNFIT` | 비합 | |
| `DROPOUT` | 탈락 | |
| `SECOND_MEET` | 2차만남 | **스페이스 없음** — 아래 참고 |
| `CONSULT_WIN` | 상담따기 | **스페이스 없음** — 아래 참고 |

> ⚠️ **LABEL에 스페이스가 없는 이유**: `MatchingScreen.vue`는 레거시 프론트를 그대로
> 옮긴 화면이라, `resDisp.includes('상담따기')`처럼 **스페이스 없는 부분 문자열**로
> 결과를 판별하는 로직이 곳곳에 있음(`showHasConsultBtn`, `POSTPONE_MARKERS` 등).
> 다른 코드 테이블(TM_RESULT_CODES 등)의 LABEL은 자연스러운 한글 띄어쓰기를 쓰지만,
> 이 두 값만 프론트 문자열 매칭에 맞춰 일부러 붙여씀. LABEL을 "2차 만남"/"상담 따기"로
> 되돌리면 프론트 필터가 깨짐 — 바꾸려면 `MatchingScreen.vue`도 같이 고쳐야 함.

`MATCH_SUB_REASON_CODES` — `CANCEL`/`UNFIT`/`DROPOUT`에만 존재(`DELAY`/`SECOND_MEET`/`CONSULT_WIN`은 세부사유 없음):

| RESULT_CODE | SUB_CODE | LABEL |
|---|---|---|
| CANCEL | `BOUNDARY_CANCEL` | 경계취소 |
| CANCEL | `CONFLICT_CANCEL` | 갈부취소 |
| CANCEL | `ENV_CANCEL` | 환경취소 |
| CANCEL | `CONTACT_LOST_CANCEL` | 연두취소 |
| UNFIT | `ENV_UNFIT` | 환경비합 |
| UNFIT | `PERSONALITY_UNFIT` | 인성비합 |
| UNFIT | `MENTAL_HEALTH` | 정신질환 |
| UNFIT | `HEALTH_UNFIT` | 건강비합 |
| DROPOUT | `BOUNDARY_DROPOUT` | 경계탈락 |
| DROPOUT | `CONFLICT_DROPOUT` | 갈부탈락 |

> `CONFLICT_CANCEL`/`CONFLICT_DROPOUT`("갈부")과 `CONTACT_LOST_CANCEL`("연두")은
> 원래 축약어라 의미를 확정할 수 없어 추정으로 코드명을 붙임 — 실제 뜻과 다르면
> 코드명만 바꾸면 됨(값 자체는 이미 저장된 데이터에 영향 없음, `LABEL`만 화면에 쓰임).

## 새 코드 테이블을 추가할 때

1. `sql/`에 다음 번호로 새 파일(`sql/12_xxx.sql` 등) — 기존 CHECK 컬럼이 있으면
   `DROP COLUMN` 후 코드 타입으로 `ADD` + FK 제약 추가(예시: `sql/11_match_result_codes.sql`).
2. `python manage.py load_sql sql/12_xxx.sql`로 실제 DB에 적용.
3. 관련 뷰(`api/views/*.py`)의 한글→코드 역매핑 딕셔너리와 표시용 JOIN을 갱신.
4. 이 문서에 표 추가.
