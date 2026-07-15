# Tech4Good 2026 — 교통약자 맞춤 이동 내비게이션

거동이 불편한 교통약자가 자신의 실제 이동 조건에 맞는 경로와 도착시간을 확인하고, 이동 중 대중교통을 놓치거나 경로에서 이탈했을 때 현재 위치를 기준으로 다시 안내받는 모바일 웹 서비스입니다.

## MVP 구조

```text
React + Vite
  → FastAPI /api/v1
     ├─ Demo Bearer 인증·가변 이동 프로필
     ├─ 지도·브라우저 장소 검색 → Kakao
     ├─ 대중교통·자동차·보행 경로 → TMAP
     ├─ 버스 도착·저상 차량 → 서울 버스 실시간 API
     ├─ 지하철 도착·엘리베이터 → 서울 열린데이터광장
     ├─ 경사·단차 → 교체 가능한 합성 접근성 어댑터
     └─ 개인화 경로·시간 계산 → Python 경로 엔진
```

서비스 품질 보장 범위는 서울시입니다. API와 데이터 모델은 다른 지역의 제공자를 어댑터로 추가할 수 있게 설계합니다.

현재는 ETA_v2 프론트와 경로 검색부터 안내·자동 재탐색 제안·완료까지의 백엔드 수직 슬라이스가 연결되어 있습니다. 이메일 회원가입·JWT·SQLite와 백엔드 장소 검색은 후속 구현 범위입니다.

## 프론트 실행

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

`frontend/.env`에 카카오 JavaScript 키를 설정합니다. 데모 로그인은 `test@eta.com / password123`이며, 상세 내용은 [프론트 README](frontend/README.md)를 참고합니다.

## 백엔드 실행

```bash
cd backend
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload
```

로컬 인증은 `Authorization: Bearer demo-token`을 사용합니다. 상세 환경변수, 테스트와 Docker 실행법은 [백엔드 README](backend/README.md)를 참고합니다.

## 문서

| 문서 | 용도 |
|---|---|
| [기능 명세](docs/functional-spec.md) | 사용자 흐름, 기능 ID, 화면 상태와 완료 조건 |
| [API 명세](docs/api-spec.md) | 엔드포인트, 인증, 공통 규칙, 오류와 상태 전이 |
| [OpenAPI](docs/openapi.yaml) | 프론트·백엔드가 공유하는 기계 판독 가능한 계약 |
| [경로 엔진 계약](docs/route-engine-contract.md) | 외부 경로를 개인화 경로로 변환하는 Python 인터페이스 |
| [인계 체크리스트](docs/handoff-checklist.md) | 역할, API 키, 데이터 출처, 시연 및 장애 대응 |
| [Mock 사용 안내](mocks/README.md) | 화면과 fixture의 연결 관계 및 사용법 |
| [백엔드 실행 안내](backend/README.md) | FastAPI 실행, 공급자 모드, 테스트와 Docker 배포 |
| [프론트 실행 안내](frontend/README.md) | Vite 환경변수, 데모 로그인과 검증 명령 |

## 프론트 개발 방법

1. `frontend/.env.example`을 `.env`로 복사하고 카카오 JavaScript 키를 설정합니다.
2. 각 탭은 처음 열릴 때 해당 `mode`의 `POST /api/v1/routes/search`를 호출하고 같은 조건은 캐시합니다.
3. API 타입과 UI 매퍼는 `frontend/src/api/`에서 관리합니다.
4. TMAP·공공데이터 키는 프론트 번들에 넣지 않습니다. 카카오맵 JavaScript 키는 허용 도메인을 제한합니다.

Mock 데이터는 TMAP 응답을 복제하지 않은 합성 데이터이며 실제 운행정보가 아닙니다.

## 핵심 원칙

- 경로는 빠른 순서보다 **이용 가능성**, 그다음 **개인화 ETA** 순으로 정렬합니다.
- 알 수 없는 시설·저상버스 상태는 `UNKNOWN`으로 표시하고 이용 가능하다고 단정하지 않습니다.
- 합성 접근성 정보는 `dataSource: SYNTHETIC_FIXTURE`로 표시해 실제 데이터와 구분합니다.
- TMAP 대중교통 경로는 시간표 기반 후보로 사용하고, 서울 버스·지하철 실시간 도착정보로 출발시각과 탑승 가능성을 다시 계산합니다.
- 위치 좌표는 안내 중 계산에만 사용하고 DB에 저장하지 않습니다.
- 일반 ETA와 개인화 ETA를 함께 보여 계산의 차이를 사용자가 이해할 수 있게 합니다.
- 택시는 경로·예상시간·예상요금만 제공하며 호출·예약·결제는 MVP에서 제외합니다.
