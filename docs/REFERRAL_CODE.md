# 지역원 유입 추천 코드 (PIONEER /event 연동)

지역원이 각자 본인 인스타 계정으로 DM을 보내고, 프로필 링크에 있는 PIONEER `/event` 링크로 유입된 신청자를 누가 데려왔는지 구별하기 위한 설계 문서.

## 목표

- 지역원별 고유 링크: `https://pioneerhq.vercel.app/event?ref=<코드>`
- 사번(`MEMBERS.MEMBER_ID`)은 URL·PIONEER·시트 어디에도 노출하지 않는다.
- 별도 테이블을 추가하지 않는다.

## 코드 생성 방식 (HMAC)

```
code = base64url( HMAC-SHA256(REFERRAL_SECRET, MEMBER_ID) )[:16]
```

- `REFERRAL_SECRET`: Ddochi2 서버에만 두는 비밀키(환경변수). PIONEER에는 넣지 않는다.
- 일반 해시(SHA-256 등)를 쓰지 않는다. 사번은 형식이 정해져 있어 대입으로 역산이 가능하다.
- 16자는 64bit라 충돌 가능성은 무시할 수준이다.
- 결과는 지역원마다 고정값이다. 비밀키를 바꾸면 전체 링크가 바뀐다.

## 코드 → 지역원 해석

- 별도 매핑 테이블 없음.
- 관리자 화면에서 `MEMBERS`를 전부 읽어 각 `MEMBER_ID`의 코드를 계산하고, 입력 코드와 매칭한다.
- 조회는 기존 `DataRouterClient`(`api/clients/data_router.py`)를 통한다.

## PIONEER 쪽 동작

1. `/event` 진입 시 `ref` 쿼리를 읽어 `sessionStorage`에 저장한다(새로고침 유지).
2. 신청 폼 제출 시 `referrer` 필드로 함께 보낸다. 값이 없거나 비어 있으면 `direct`.
3. Apps Script `doPost`가 시트의 `유입코드` 컬럼에 기록한다.
4. `/admin`은 시트 헤더를 그대로 보여주므로 `유입코드` 컬럼이 자동으로 표시된다.

PIONEER는 코드 문자열만 받고 저장한다. 코드→이름 해석은 Ddochi2 관리자 쪽에서만 한다.

## 주의사항

- 코드는 귀속(누가 데려왔는지) 표시용이지 인증이 아니다. 코드를 아는 사람은 누구나 그 지역원 이름으로 신청을 넣을 수 있다.
- 이상 패턴은 시트에 신청 시각·IP 등을 같이 남겨서 확인한다.
- 특정 지역원 링크만 무효화하려면 테이블이 필요하다. 필요해지면 그때 추가한다.

## 상태

해석 위치는 원안(또치 관리자 화면) 대신 PIONEER `/admin`에 이름까지 표시하기로 함(2026-10-03). PIONEER 서버가
`POST /api/referral/resolve`(헤더 `X-Pioneer-Key`, 공유 키 `PIONEER_INTERNAL_KEY`)를 서버 간 호출하고, 응답은 이름·지역뿐(사번 없음).
지역원은 또치 앱 홈의 "내 추천 링크"(`POST /api/referral/my-link`)로 자기 링크를 복사.

- [x] Ddochi2: 코드 생성/해석 헬퍼 (`api/util/referral.py`) + API (`api/views/referral.py`)
- [ ] Ddochi2: `REFERRAL_SECRET`, `PIONEER_INTERNAL_KEY` 환경변수 설정 (VM `.env`)
- [x] PIONEER: `/event`에서 `ref` 읽기 + `sessionStorage` 저장
- [x] PIONEER: 제출 시 `referrer` 전송
- [ ] Apps Script: `유입코드` 컬럼 기록
- [x] 관리자: PIONEER `/admin`에 `유입자` 컬럼 (`DDOCHI_API_URL`, `PIONEER_INTERNAL_KEY` Vercel env 필요)
