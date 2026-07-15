# My ETA

> 교통약자를 위한 개인화 배리어프리 길찾기 서비스
> 하나금융그룹 x SK텔레콤 Tech4Good 2026 - 15조 피프틴피프틴

My ETA는 노약자, 휠체어 이용자, 임산부 등 교통약자의 실제 보행속도와 이동 편의 조건을 반영해 경로와 예상 도착시간을 안내하는 모바일 웹 서비스입니다.

일반 지도 서비스의 획일적인 보행속도, 갱신이 늦은 이동편의시설 정보, 저상버스 탑승 가능 여부가 반영되지 않는 문제를 해결합니다. 사용자가 대중교통을 놓치거나 경로에서 이탈하면 현재 위치를 기준으로 경로와 ETA를 다시 계산합니다.

## 프로젝트 소개

교통약자에게 이동은 단순한 길찾기가 아니라 보행속도, 계단과 경사, 엘리베이터 위치, 저상버스 도착 여부를 함께 고려해야 하는 계획입니다.

My ETA는 다음 세 가지 문제를 중심으로 설계했습니다.

- 표준 보행속도와 실제 이동속도의 차이로 발생하는 ETA 오차
- 지하철 엘리베이터 등 이동편의시설 정보의 부족과 갱신 지연
- 저상버스 탑승 가능 여부를 고려하지 않는 획일적인 경로 안내

서비스 품질 보장 범위는 서울시이며, 다른 지역의 데이터 공급자를 어댑터로 추가할 수 있도록 구성했습니다.

## 주요 기능

### 1. 개인별 이동속도 보정

- 이동 유형과 보조기구, 계단 회피, 엘리베이터·저상버스 필수 조건을 프로필로 설정합니다.
- 사용자의 평소 보행속도와 안내 중 수집한 유효 속도 표본으로 도보 구간 ETA를 보정합니다.
- 경사와 보행환경을 반영해 일반 ETA와 개인화 ETA를 함께 제공합니다.

### 2. 공공데이터 기반 이동편의시설 안내

- 서울 버스 실시간 도착정보와 저상버스 여부를 경로에 반영합니다.
- 지하철 실시간 도착정보, 엘리베이터 위치와 접근성 정보를 제공합니다.
- 확인되지 않은 정보는 이용 가능으로 단정하지 않고 `UNKNOWN` 또는 주의 상태로 표시합니다.

### 3. ETA 기반 교통수단 최적화

- 대중교통, 도보, 택시 경로를 시간적·비용적·접근성 관점에서 비교합니다.
- 저상버스 탑승 가능성과 정류장까지의 개인화 ETA를 함께 계산합니다.
- 이용 가능한 대중교통 경로가 없으면 택시 또는 장애인 콜택시 대안을 제시합니다.

### 4. 이동 중 안내와 재탐색

- 선택한 경로를 지도와 구간별 상세 안내로 제공합니다.
- 경로 이탈이나 대중교통 놓침을 감지하면 재탐색을 제안합니다.
- 재탐색 시 현재 위치를 새 출발점으로 사용하고 경로와 ETA를 갱신합니다.
- 원본 위치 좌표는 안내 중 계산에만 사용하고 영구 저장하지 않습니다.

## 서비스 흐름

```mermaid
flowchart LR
    A["이동 유형·접근성 조건"] --> B["목적지 검색"]
    B --> C["기본 경로·실시간 정보 수집"]
    C --> D["개인화 ETA·접근성 계산"]
    D --> E["지도·상세 경로 안내"]
    E --> F{"재탐색 필요?"}
    F -- "예" --> C
    F -- "아니요" --> G["경로 유지·안내 완료"]
```

## 사용 기술

| 영역 | 기술 및 데이터 |
|---|---|
| 프론트엔드 | React 19, TypeScript, Vite, Tailwind CSS |
| 백엔드 | Python 3.12, FastAPI, Pydantic, HTTPX, Uvicorn |
| 지도·장소 검색 | Kakao Maps JavaScript SDK, Kakao Local API |
| 경로 탐색 | TMAP 대중교통·자동차·보행 경로 API |
| 실시간 교통 | 서울 버스 도착정보, 저상버스 정보, 서울 지하철 실시간 도착정보 |
| 이동편의시설 | 서울 열린데이터광장·공공데이터포털의 엘리베이터 및 교통약자 이용정보 |
| 개인화 엔진 | Python 기반 보행속도 학습, 접근성 판정, 개인화 ETA 계산 |
| 테스트·계약 | Pytest, Vitest, Ruff, OpenAPI 3.1, JSON Schema |

## 시스템 구성

```text
React + Vite
  -> FastAPI /api/v1
     |- 데모 인증·이동 프로필
     |- 지도·장소 검색 -> Kakao
     |- 대중교통·자동차·보행 경로 -> TMAP
     |- 버스 도착·저상 차량 -> 서울 버스 API
     |- 지하철 도착·엘리베이터 -> 서울 열린데이터광장
     `- 접근성 판정·개인화 ETA -> Python 경로 엔진
```

## 실행 방법

### 1. 저장소 받기

```bash
git clone https://github.com/tech4good-2026/eta.git
cd eta
```

### 2. 프론트엔드 실행

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

`frontend/.env`에 카카오 JavaScript 키를 설정합니다.

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_KAKAO_MAP_APP_KEY=your_kakao_javascript_key
```

카카오 Developers에서 `http://localhost:5173`을 Web 허용 도메인으로 등록해야 합니다.

### 3. 백엔드 실행

```bash
cd backend
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

실제 TMAP·서울 공공데이터를 사용할 때는 `backend/.env`를 다음과 같이 설정합니다.

```env
ROUTE_PROVIDER=tmap
DEMO_TOKEN=demo-token
CORS_ORIGINS=["http://localhost:5173"]
TMAP_APP_KEY=your_tmap_app_key
SEOUL_API_KEY=your_seoul_api_key
SEOUL_SUBWAY_API_KEY=your_seoul_subway_api_key
SEOUL_BUS_API_KEY=your_seoul_bus_api_key
```

API 키가 없을 때는 `ROUTE_PROVIDER=mock`으로 실행할 수 있습니다. `.env` 파일과 실제 API 키는 저장소에 커밋하지 않습니다.

## 접속 및 확인

| 구분 | 주소 또는 값 |
|---|---|
| 프론트엔드 | <http://localhost:5173> |
| 백엔드 Health | <http://localhost:8000/health> |
| Swagger UI | <http://localhost:8000/docs> |
| 데모 계정 | `test@eta.com` / `password123` |
| API 인증 | `Authorization: Bearer demo-token` |

### 테스트

```bash
# 프론트엔드
cd frontend
npm test -- --run
npm run lint
npm run build

# 백엔드
cd ../backend
uv run pytest
uv run ruff check .
```

## 팀 구성 및 역할

**팀명:** 15조 피프틴피프틴<br>
**팀원:** 권유철, 박예진, 김서연, 성진혁, 박재형, 김강민, 이승연

| 팀원 | 역할 및 기여 |
|---|---|
| 권유철, 박예진, 이승연 | PM·서비스 기획·리서치 - 문제 정의, 서비스 방향 및 핵심 기능 설계, 발표 시나리오 구성, 발표와 발표자료 제작 |
| 김서연, 김강민, 박재형, 성진혁 | 프로덕트 개발 - UI/UX 설계, 프론트엔드·백엔드 개발, 외부 API 연동, AI·개인화 알고리즘 구현, 기능 QA |

## 문서

| 문서 | 내용 |
|---|---|
| [기능 명세](docs/functional-spec.md) | 사용자 흐름, 화면 상태, 완료 조건 |
| [API 명세](docs/api-spec.md) | 엔드포인트, 인증, 오류와 상태 전이 |
| [OpenAPI](docs/openapi.yaml) | 프론트·백엔드 공통 API 계약 |
| [경로 엔진 계약](docs/route-engine-contract.md) | 개인화 경로 엔진 입출력 인터페이스 |
| [시연·인계 체크리스트](docs/handoff-checklist.md) | API 키, 데이터 출처, 대표 시나리오와 장애 대응 |

## 데이터 원칙

- 경로는 이용 가능성, 개인화 ETA 순으로 정렬합니다.
- 실제·시간표·추정·미확인·합성 데이터를 명확히 구분합니다.
- 외부 데이터가 없을 때 이용 가능 여부를 임의로 생성하지 않습니다.
- TMAP 경로 캐시는 10분만 유지하며 원본 응답을 장기간 저장하지 않습니다.
- 위치 좌표는 안내 계산에만 사용하고, 안내 완료 후 유효한 속도 집계만 남깁니다.
