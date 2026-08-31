# Ddochi Backend (Django rebuild)

`Ddochi/services/main`(Express, 90+ REST 엔드포인트)을 Django로 다시 짜는 프로젝트. `data_router`(Go, Oracle ADB 게이트웨이)는 원본 그대로 가져와서 사용하고, Django는 Oracle에 직접 붙지 않고 항상 `data_router`를 거칩니다.

라우트 포팅은 진행 중입니다. `api/urls.py`에 Express의 237개 엔드포인트가 전부 501 스텁으로 이미 매핑돼있고, 일부만(`api/views/shed_users.py` 등) 실제 로직이 붙어있습니다. 자세한 아키텍처는 [CLAUDE.md](CLAUDE.md) 참고.

## 사전 준비물

- Python 3.12
- Docker Desktop (data_router 컨테이너 실행용)
- Oracle wallet — dev DB(`univdbdev_high`)용 wallet 파일 (`wallet/` 디렉토리, git에는 안 올라감)

## 환경 설정

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`.env` 파일 생성 (git에 안 올라감 — `.gitignore` 처리됨):

```bash
DB_NAME=univdbdev_high
DB_USER=ADMIN
DB_PASSWORD=<wallet 계정 비밀번호>
TNS_ADMIN=/절대/경로/Ddochi_dev/wallet

DJANGO_SECRET_KEY=<임의의 긴 랜덤 문자열>
DJANGO_DEBUG=True

DATA_ROUTER_URL=http://localhost:8080
DATA_ROUTER_TOKEN=<openssl rand -hex 32 로 생성>
DATA_ROUTER_CALLER=django-main

SHED_INTERNAL_KEY=<shed 프로젝트(Vercel)의 SHED_INTERNAL_KEY와 동일한 값>
```

`wallet/` 디렉토리에 Oracle wallet 파일(`cwallet.sso`, `tnsnames.ora`, `sqlnet.ora` 등)을 넣습니다. `wallet/sqlnet.ora`의 `WALLET_LOCATION`이 이 프로젝트의 절대경로를 하드코딩하고 있으므로, 경로가 다르면 그 안의 경로도 맞춰서 고쳐야 합니다.

## 로컬에서 실행하기

**1. data_router (Go) 띄우기** — Oracle 접근은 전부 이걸 거칩니다.

```bash
docker compose up -d --build data_router      # localhost:8080, dev DB(univdbdev_high)
```

**2. Django 내부 테이블 마이그레이션** (admin/auth/sessions — sqlite. Oracle이 아님, 아래 "왜 sqlite인가" 참고)

```bash
python manage.py migrate
```

**3. dev DB에 스키마 올리기** (최초 1회, 또는 `sql/`에 새 파일 추가했을 때)

```bash
python manage.py load_sql sql/01_users.sql
```

**4. 서버 실행**

```bash
python manage.py runserver 127.0.0.1:8000
```

`http://127.0.0.1:8000/health` 또는 `/api/healthz`(실제 DB 왕복 확인용)로 동작 확인.

### 왜 Django가 sqlite를 쓰는가

`config/settings.py`의 `DATABASES`는 Oracle이 아니라 `db.sqlite3`를 가리킵니다. Django 자신의 내부 테이블(`admin`/`auth`/`sessions`)만 여기 저장하고, 실제 서비스 데이터는 전부 `data_router` 경유로만 접근합니다. dev wallet의 `ewallet.pem`이 비밀번호로 잠겨있어서, `DATABASES`를 Oracle로 바로 돌리면 `runserver`가 마이그레이션 상태를 확인하려다 PEM 패스프레이즈 입력 대기로 무한정 멈춥니다 — 이 구조는 우회가 아니라 그 문제의 해결책입니다.

## 자주 쓰는 명령어

```bash
python manage.py check                         # 시스템 체크
python manage.py dr_ping                        # data_router 연결 확인 (ping + SELECT SYSDATE)
python manage.py load_sql sql/<file>.sql         # DDL/시드 파일을 data_router 경유로 실행
python manage.py import_prod_team <team_id>      # 프로덕션 USERS 중 한 팀만 dev로 복사 (읽기 전용)
```

## 프로덕션 데이터 가져오기 (선택)

특정 팀 인원만 프로덕션에서 dev로 복사하고 싶을 때, 프로덕션 wallet(`Ddochi/wallet_v2`)을 가리키는 읽기 전용 컨테이너를 추가로 띄웁니다. 자격증명은 이 프로젝트의 `.env`가 아니라 `Ddochi/.env`에서 그때그때 가져옵니다.

```bash
set -a
source .env
source <(grep -E "^ORACLE_(USER|PASSWORD|SERVICE|WALLET_PASSWORD)=" ../Ddochi/.env | sed 's/^ORACLE_/PROD_ORACLE_/')
set +a
docker compose up -d --build data_router_prod   # localhost:8081, prod DB

python manage.py import_prod_team team_4
```

이 컨테이너는 `SELECT`만 쓰도록 되어있고, 끝나면 `docker compose stop data_router_prod`로 내려두세요.

## 지식 그래프 (graphify)

```bash
/graphify .
```

`graphify-out/`에 인터랙티브 그래프(`graph.html`), 리포트(`GRAPH_REPORT.md`), portable 그래프 데이터(`graph.json`)가 생성됩니다. 캐시/개인 토큰비용/로컬 venv 경로 같은 머신-로컬 파일만 `.gitignore`로 제외하고, 나머지는 git에 커밋해서 팀원과 공유합니다.

## 배포

아직 배포 파이프라인은 없습니다. `requirements.txt`에 `gunicorn`이 들어있어 프로덕션 WSGI 서버로 쓸 것을 염두에 두고는 있지만, Dockerfile/CI/systemd 등 실제 배포 설정은 이 저장소에 아직 존재하지 않습니다. 참고로 원본 `Ddochi` 프로젝트의 `data_router`는 Cloud Run과 VM(systemd) 두 가지 배포 방식을 문서화해뒀습니다 (`data_router/README.md`) — Django 쪽 배포 전략을 정할 때 참고할 수 있습니다.
