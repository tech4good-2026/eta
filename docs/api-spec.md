# API 명세서

이 문서는 사람이 읽는 API 요약입니다. 필드 수준의 단일 기준은 [OpenAPI 3.1 문서](openapi.yaml)입니다.

> 현재 백엔드 수직 슬라이스는 프로필 조회, 경로 검색·조회, 안내 시작·위치 처리·재탐색을 구현합니다. 인증은 `Bearer demo-token`을 사용합니다. 회원가입·로그인·프로필 수정·장소 검색·안내 완료는 프론트 계약과 후속 범위로 유지됩니다.

## 1. 공통 규칙

- Base URL: `/api/v1`
- Content-Type: `application/json`
- JSON 필드: `camelCase`
- Enum 값: 대문자 `SNAKE_CASE`
- 시각: UTC offset이 포함된 ISO 8601. 서울 시각 예: `2026-07-15T14:00:00+09:00`
- 지속시간: 초(`Sec`), 거리: 미터(`M`), 속도: m/s(`Mps`), 요금: 원(`Krw`)
- 좌표계: WGS84, 객체는 `{ "latitude", "longitude" }`
- GeoJSON: `LineString.coordinates`는 `[longitude, latitude]`
- 인증: `Authorization: Bearer <accessToken>`
- 현재 구현 인증: `Bearer demo-token`
- 후속 인증 계약: JWT 만료는 발급 후 24시간이며 만료 후 다시 로그인합니다.

## 2. 엔드포인트

| Method | Path | 인증 | 용도 |
|---|---|---:|---|
| POST | `/auth/signup` | 아니요 | 이메일 회원가입과 JWT 발급 |
| POST | `/auth/login` | 아니요 | 로그인과 JWT 발급 |
| GET | `/users/me` | 예 | 현재 사용자 조회 |
| DELETE | `/users/me` | 예 | 계정·프로필·속도 집계 삭제 |
| GET | `/users/me/profile` | 예 | 이동 프로필 조회 |
| PUT | `/users/me/profile` | 예 | 이동 프로필 전체 저장 |
| GET | `/places/search` | 예 | 카카오 기반 장소 검색 |
| POST | `/routes/search` | 예 | 모드 하나의 개인화 경로 검색 |
| GET | `/routes/{routeId}` | 예 | 만료 전 경로 상세 조회 |
| POST | `/navigation/sessions` | 예 | 안내 세션 시작 |
| POST | `/navigation/sessions/{sessionId}/position` | 예 | 현재 위치 처리 및 이탈 판단 |
| POST | `/navigation/sessions/{sessionId}/reroute` | 예 | 사용자 확인 후 경로 재탐색 |
| POST | `/navigation/sessions/{sessionId}/complete` | 예 | 안내 종료와 보행속도 학습 |

## 3. 인증과 프로필

회원가입과 로그인 응답은 동일한 `AuthResponse`를 사용합니다.

```json
{
  "accessToken": "mock.jwt.token",
  "tokenType": "Bearer",
  "expiresInSec": 86400,
  "user": {
    "userId": "usr_01",
    "email": "demo@example.com",
    "profileCompleted": false,
    "createdAt": "2026-07-15T13:00:00+09:00"
  }
}
```

`PUT /users/me/profile`은 프로필 전체를 교체합니다. 보행속도는 서버 관리 필드이므로 요청에 포함하지 않습니다.

```json
{
  "travelerTypes": ["MOBILITY_IMPAIRED"],
  "mobilityAids": ["MANUAL_WHEELCHAIR"],
  "preferences": {
    "avoidStairs": true,
    "elevatorRequired": true,
    "lowFloorBusRequired": true,
    "avoidSteepSlopes": true
  }
}
```

## 4. 장소 검색

`GET /places/search?q=서울역&latitude=37.5547&longitude=126.9707&page=1&size=10`

- `q`: 2~100자 검색어
- 중심 좌표는 선택이며 가까운 결과 정렬에 사용합니다.
- `page`: 1 이상, `size`: 1~15
- 프론트에는 공급자 원본 대신 `Place` 배열을 반환합니다.

## 5. 경로 검색

`POST /routes/search`는 탭 하나에 해당하는 모드만 요청합니다.

```json
{
  "origin": {
    "name": "서울역",
    "coordinate": { "latitude": 37.5547, "longitude": 126.9707 }
  },
  "destination": {
    "name": "잠실역",
    "coordinate": { "latitude": 37.5133, "longitude": 127.1001 }
  },
  "mode": "TRANSIT",
  "departureAt": "2026-07-15T14:00:00+09:00"
}
```

응답의 정렬 순서는 `ACCESSIBLE → CAUTION → UNAVAILABLE`이며 같은 상태에서는 `personalizedDurationSec` 오름차순입니다.

```json
{
  "searchId": "search_001",
  "mode": "TRANSIT",
  "status": "SUCCESS",
  "generatedAt": "2026-07-15T14:00:00+09:00",
  "expiresAt": "2026-07-15T14:10:00+09:00",
  "routes": [],
  "fallbackModes": []
}
```

`Route`는 요약과 `WALK | BUS | SUBWAY | TAXI` 구간 배열을 포함합니다. 각 구간은 일반/개인화 시간과 지도용 `LineString`을 갖습니다.

### 정보 상태

- `accessibilityStatus`: 경로 전체 이용 가능성
- `dataConfidence`: 접근성 정보의 `VERIFIED | ESTIMATED | UNKNOWN`
- `timeSource`: 출발시각의 `REALTIME | SCHEDULED | ESTIMATED | UNKNOWN`
- `facilityStatus`: 시설의 `AVAILABLE | UNAVAILABLE | UNKNOWN`
- `lowFloorStatus`: `CONFIRMED | EXPECTED | NOT_LOW_FLOOR | UNKNOWN`
- `dataSource`: `TMAP | SEOUL_OPEN_DATA | SYNTHETIC_FIXTURE | TEAM_ENGINE | UNKNOWN`

접근 가능한 경로가 없는 것은 정상 검색 결과입니다.

```json
{
  "searchId": "search_none_001",
  "mode": "TRANSIT",
  "status": "NO_ACCESSIBLE_ROUTE",
  "generatedAt": "2026-07-15T14:00:00+09:00",
  "expiresAt": "2026-07-15T14:10:00+09:00",
  "routes": [],
  "fallbackModes": ["TAXI"],
  "notices": [
    {
      "code": "LOW_FLOOR_BUS_UNAVAILABLE",
      "severity": "WARNING",
      "message": "필수 조건을 충족하는 저상버스 경로를 찾지 못했습니다."
    }
  ]
}
```

## 6. 안내 세션

### 시작

`POST /navigation/sessions`

```json
{ "routeId": "route_transit_001" }
```

유효한 경로만 시작할 수 있습니다. 만료된 경로는 `410 ROUTE_EXPIRED`입니다.

### 위치 처리

`POST /navigation/sessions/{sessionId}/position`

```json
{
  "coordinate": { "latitude": 37.5657, "longitude": 126.9770 },
  "recordedAt": "2026-07-15T14:12:10+09:00",
  "accuracyM": 18.0
}
```

프론트는 전경에서 최대 5초에 한 번 전송합니다. 서버는 현재 안내 판단과 속도 집계에 사용한 뒤 원본 위치를 저장하지 않습니다. 사용자 확인 전에는 `routeRevision`과 경로를 변경하지 않습니다.

### 재탐색

`POST /navigation/sessions/{sessionId}/reroute`

```json
{
  "reason": "MISSED_TRANSIT",
  "currentLocation": {
    "coordinate": { "latitude": 37.5657, "longitude": 126.9770 },
    "recordedAt": "2026-07-15T14:12:10+09:00",
    "accuracyM": 25.0
  },
  "currentStation": {
    "providerPlaceId": "station_cityhall_132",
    "name": "시청역",
    "coordinate": { "latitude": 37.5657, "longitude": 126.9770 }
  }
}
```

`currentLocation` 또는 `currentStation` 중 하나는 반드시 있어야 합니다. 두 값이 모두 있으면 `currentStation` 좌표를 GPS보다 우선합니다. 성공하면 같은 세션에서 `routeRevision`을 1 증가시키고 새 경로를 반환합니다.

### 완료

`POST /navigation/sessions/{sessionId}/complete`

```json
{ "reason": "ARRIVED", "completedAt": "2026-07-15T14:49:00+09:00" }
```

서버가 보유한 임시 집계를 이용해 프로필 속도를 갱신합니다. 유효 표본이 없으면 기존 속도를 유지합니다.

## 7. 오류

```json
{
  "error": {
    "code": "UPSTREAM_UNAVAILABLE",
    "message": "현재 경로 정보를 불러오지 못했습니다.",
    "requestId": "req_01",
    "details": { "provider": "TMAP", "retryable": true }
  }
}
```

| HTTP | code | 상황 |
|---:|---|---|
| 400 | `INVALID_REQUEST` | 형식상 잘못된 요청 |
| 401 | `INVALID_CREDENTIALS`, `UNAUTHORIZED` | 로그인 실패 또는 토큰 문제 |
| 404 | `USER_NOT_FOUND`, `ROUTE_NOT_FOUND`, `SESSION_NOT_FOUND` | 대상 없음 |
| 409 | `EMAIL_ALREADY_EXISTS`, `SESSION_ALREADY_COMPLETED` | 상태 충돌 |
| 410 | `ROUTE_EXPIRED` | 10분 유효시간 만료 |
| 422 | `VALIDATION_ERROR`, `PROFILE_REQUIRED` | 필드 검증 또는 프로필 필요 |
| 429 | `RATE_LIMITED` | 우리 서버 또는 외부 API 호출 제한 |
| 502 | `UPSTREAM_INVALID_RESPONSE` | 외부 API의 잘못된 응답 |
| 503 | `UPSTREAM_UNAVAILABLE` | 외부 API 장애·타임아웃 |

## 8. 캐시와 보안

- 공급자 경로 원본과 정규화 경로는 검색 후 10분만 보관합니다.
- 만료된 `routeId`로 상세조회·안내 시작을 할 수 없습니다.
- TMAP·공공데이터 키는 백엔드 환경변수로만 관리합니다.
- TMAP 후보 경로만 10분 캐시하고 버스·지하철 실시간 도착정보는 경로 검색마다 다시 보강합니다.
- 개인화 엔진은 사용자의 승차 지점 도착 예상시각에 60초 여유를 더한 뒤 탑승 가능한 실시간 차량을 선택합니다.
- 카카오맵 JavaScript 키는 프론트에서 사용하되 도메인을 제한합니다.
- 비밀번호는 평문·복호화 가능한 형태로 저장하지 않습니다.
- 이메일·사용자 ID·이동 프로필은 외부 경로 공급자에게 전송하지 않습니다.
