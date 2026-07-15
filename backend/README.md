# FastAPI 백엔드

현재 구현은 해커톤 수직 슬라이스입니다. `Bearer demo-token`과 고정 이동 프로필을 사용하며 회원가입·JWT·SQLite는 후속 범위입니다.

## 로컬 실행

```bash
cd backend
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload
```

- Health: `GET http://localhost:8000/health`
- Swagger UI: `http://localhost:8000/docs`
- API Base: `http://localhost:8000/api/v1`
- 인증 헤더: `Authorization: Bearer demo-token`

## 공급자 모드

- `ROUTE_PROVIDER=mock`: 외부 키 없이 세 경로 모드와 안내 흐름을 합성 데이터로 실행합니다.
- `ROUTE_PROVIDER=tmap`: TMAP 대중교통·자동차·보행 API와 서울시 데이터를 호출합니다. `TMAP_APP_KEY`, 서울 일반 데이터용 `SEOUL_API_KEY`, 실시간 지하철용 `SEOUL_SUBWAY_API_KEY`가 필요하며 장애 시 Mock으로 자동 전환하지 않습니다.
- `SEOUL_BUS_API_KEY`: 공공데이터포털에서 받은 **디코딩 인증키**입니다. 선택값이지만 없으면 버스 실시간 도착과 저상 차량 여부가 `UNKNOWN`으로 남습니다.
- TMAP 대중교통은 시간표 기반 경로 후보로 사용합니다. 서울 버스 도착정보의 `exps1/2`, `busType1/2`와 서울 지하철 실시간 도착정보를 합쳐 실제 출발시각을 선택합니다.
- 개인 보행속도로 승차 지점 도착시각을 계산한 뒤 60초의 탑승 여유가 있는 차량만 선택합니다. 저상버스 필수 사용자는 다음 두 차량 중 탑승 가능한 저상 차량을 우선 사용합니다.
- TMAP 후보 경로는 10분 캐시하지만 실시간 보강은 경로 검색마다 다시 수행합니다. 경사·단차만 현재 `SYNTHETIC_FIXTURE`입니다.

### 서울 버스 API 준비

공공데이터포털에서 아래 두 서비스를 활용 신청한 뒤 동일한 디코딩 인증키를 `SEOUL_BUS_API_KEY`에 넣습니다.

- [서울특별시 노선정보조회 서비스](https://www.data.go.kr/data/15000193/openapi.do): TMAP 노선명과 승차 정류장을 서울 버스 ID로 변환
- [서울특별시 버스도착정보조회 서비스](https://www.data.go.kr/data/15000314/openapi.do): 실제 도착예정시간과 저상 차량 유형 조회

버스 키가 없거나 조회에 실패해도 TMAP 경로를 합성 데이터로 바꾸지 않습니다. 해당 정보만 `UNKNOWN`과 주의 경고로 내려갑니다.

## 테스트

```bash
uv run pytest
uv run ruff check .
```

팀원의 개인화 로직은 `PersonalizationEngine` 프로토콜을 구현해 `BaselinePersonalizationEngine` 대신 주입하면 됩니다. API 응답 모델은 바뀌지 않습니다.

## Docker

저장소 루트에서 실행합니다.

```bash
docker build -t tech4good-backend .
docker run --rm -p 8000:8000 -e ROUTE_PROVIDER=mock tech4good-backend
```

Render·Railway에서는 이 Dockerfile을 사용하고 배포 환경변수에 CORS와 공급자 키를 등록합니다. 프로세스 메모리 저장소이므로 재시작 시 경로·안내 세션이 초기화됩니다.
