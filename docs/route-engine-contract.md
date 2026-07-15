# 개인화 경로 엔진 계약

## 1. 목적과 경계

개인화 엔진은 FastAPI 프로세스 안에서 호출되는 순수 Python 구성요소입니다. TMAP·Kakao·서울 공공데이터의 인증, HTTP 호출, 재시도와 원본 응답 파싱은 어댑터의 책임입니다. 엔진은 정규화된 후보 경로와 접근성 맥락만 입력받습니다.

```python
def personalize_routes(
    provider_routes: list[ProviderRoute],
    profile: UserProfile,
    context: AccessibilityContext,
    requested_at: datetime,
) -> list[Route]:
    """접근성 상태와 개인화 ETA가 계산되고 정렬된 경로를 반환한다."""
```

함수는 네트워크와 DB를 호출하지 않으며 동일 입력에 동일 출력을 반환해야 합니다.

현재 구현 경계는 `backend/app/personalization.py`의 `PersonalizationEngine` 프로토콜입니다. 팀원 모듈은 이 프로토콜을 구현하고 `build_container()`의 엔진 주입만 교체합니다.

## 2. 입력 모델

### `UserProfile`

| 필드 | 타입 | 설명 |
|---|---|---|
| `travelerTypes` | `set[TravelerType]` | 사용자 유형 복수선택 |
| `mobilityAids` | `set[MobilityAid]` | 보조기구 복수선택 |
| `walkingSpeedMps` | `float` | 0보다 큰 현재 개인 속도 |
| `avoidStairs` | `bool` | 계단 회피 |
| `elevatorRequired` | `bool` | 지하철 엘리베이터 필수 |
| `lowFloorBusRequired` | `bool` | 저상버스 필수 |
| `avoidSteepSlopes` | `bool` | 급경사 회피 |

### `ProviderRoute`

공급자에 무관한 경로 후보입니다.

- `providerRouteId`, `mode`, `provider`, `standardDurationSec`, `totalDistanceM`
- `fareKrw`, `departureAt`, `arrivalAt`, `timeSource`
- `legs: list[ProviderLeg]`
- `ProviderLeg` 공통값: `mode`, `start`, `end`, `distanceM`, `standardDurationSec`, `geometry`
- 버스 상세값: 노선·정류장 ID, 노선명, 승하차 정류장
- 지하철 상세값: 호선·역 ID, 호선명, 승하차역
- 도보 상세값: 보행 단계, 공급자 설명
- 택시 상세값: 자동차 시간·거리·예상요금

어댑터는 원본 linestring을 WGS84 GeoJSON `LineString`으로 바꾸고 시간·거리·요금 단위를 공통 단위로 변환해야 합니다.

### `AccessibilityContext`

후보 경로에서 참조하는 접근성 데이터의 매핑입니다.

- `busAccessibilityByRouteAndStop`: 저상버스 `CONFIRMED | EXPECTED | NOT_LOW_FLOOR | UNKNOWN`과 실시간 차량별 출발 후보
- `subwayAccessibilityByStation`: 승하차역 엘리베이터 상태와 호선별 실시간 출발 후보
- `stationFacilities`: 역별 엘리베이터·휠체어리프트 상태와 위치
- `walkingSegments`: 보행 구간별 계단 여부, 최대 경사, 통행 가능 상태
- 각 값은 `dataConfidence: VERIFIED | ESTIMATED | UNKNOWN`, `observedAt`, `source`를 가집니다.
- 실제 보행환경 데이터가 없으면 `UnknownWalkwaySource`가 nullable 필드를 미확인 상태로 유지하며, 엔진은 확인되지 않은 값으로 환경 패널티나 `계단 없음` 판정을 만들지 않습니다.

## 3. 출력 모델

`PersonalizedRoute`는 공개 OpenAPI의 `Route`와 필드·Enum이 동일해야 합니다.

- 원본 `standardDurationSec`을 보존합니다.
- `personalizedDurationSec`과 구간별 개인화 시간을 계산합니다.
- `accessibilityStatus`, `warnings`, `unavailableReasons`를 계산합니다.
- 원본 경로 ID와 공급자 원본 응답은 외부 응답에 포함하지 않습니다.
- 최종 정렬은 `ACCESSIBLE → CAUTION → UNAVAILABLE`, 같은 상태에서는 개인화 시간이 빠른 순입니다.

## 4. 판정 규칙

### 보행시간

1. 도보 구간의 기본 개인화 시간은 `ceil(distanceM / walkingSpeedMps)`입니다.
2. 경사·노면 등 추가 보정은 구간 단위로 적용하되 결과는 기본 개인화 시간보다 짧아질 수 없습니다.
3. 원본 공급자의 도보시간과 계산값 중 더 큰 값을 사용해 과도하게 낙관적인 ETA를 방지합니다.

### 접근성 필수 조건

- `avoidStairs=true`인데 계단이 확인되면 `UNAVAILABLE`입니다.
- `elevatorRequired=true`인데 필요한 역의 엘리베이터가 `UNAVAILABLE`이면 `UNAVAILABLE`입니다.
- `lowFloorBusRequired=true`인데 해당 차량이 `NOT_LOW_FLOOR`이면 `UNAVAILABLE`입니다.
- 필수 항목이 `UNKNOWN`이면 이용 가능하다고 단정하지 않고 `CAUTION`과 확인 경고를 부여합니다.
- `avoidSteepSlopes=true`인데 급경사 구간이 확인되면 다른 경로가 있을 경우 해당 경로를 `CAUTION` 이하로 내립니다. 정확한 경사 임계값은 접근성 데이터 어댑터가 `isSteep`으로 정규화합니다.

### ETA와 탑승 가능성

- 전체 개인화 ETA는 구간별 개인화 시간과 대기·환승시간의 합입니다.
- 개인화된 도보 도착시각이 예정 탑승시각 이후면 해당 탑승편을 이용 가능한 것으로 표시하지 않습니다.
- 다음 편으로 조정할 수 있으면 ETA와 대기시간을 갱신합니다.
- 조정할 수 없으면 경로를 `UNAVAILABLE`로 만들고 `MISSED_CONNECTION_RISK` 사유를 추가합니다.

## 5. 경고 코드

- `PERSONALIZED_TIME_LONGER`
- `LOW_FLOOR_BUS_UNKNOWN`, `LOW_FLOOR_BUS_UNAVAILABLE`
- `ELEVATOR_UNKNOWN`, `ELEVATOR_UNAVAILABLE`
- `STAIRS_ON_ROUTE`, `STEEP_SLOPE`, `WALKWAY_DATA_UNKNOWN`
- `MISSED_CONNECTION_RISK`, `LONG_WALK_DISTANCE`

경고는 코드, `INFO | WARNING | CRITICAL` 심각도, 사용자 문구와 선택적 `legId`를 가집니다.

## 6. 재탐색 계약

재탐색은 기존 결과를 잘라 쓰지 않고 새 출발점과 목적지로 공급자 경로를 다시 요청한 뒤 동일 엔진을 실행합니다.

- `currentStation`이 제공되면 역 좌표를 출발점으로 사용합니다.
- 그렇지 않으면 `currentLocation.coordinate`를 사용합니다.
- 기존 프로필 스냅샷이 아니라 재탐색 시점의 최신 프로필을 사용합니다.
- 성공한 결과는 안내 세션의 `routeRevision`을 1 증가시킵니다.
- 경로가 없으면 세션은 유지하고 `NO_ACCESSIBLE_ROUTE`와 택시 대안을 반환합니다.

## 7. 테스트 벡터

1. 같은 거리에서 `walkingSpeedMps`가 낮을수록 개인화 시간이 증가합니다.
2. 계단 회피 사용자의 계단 포함 경로는 `UNAVAILABLE`입니다.
3. 엘리베이터 필수 사용자의 시설 상태가 `UNKNOWN`이면 `CAUTION`입니다.
4. 저상버스 필수 사용자의 일반버스는 `UNAVAILABLE`입니다.
5. 개인화된 승차 지점 도착시각에서 60초 이상 여유가 있는 실시간 차량만 선택하고, 대기시간을 최종 ETA에 포함합니다.
5. 접근성 상태가 같으면 개인화 시간이 빠른 경로가 먼저입니다.
6. 놓친 편 이후 다음 편이 있으면 새 대기시간과 ETA가 반영됩니다.
7. 모든 필수 경로가 불가능하면 빈 경로와 택시 대안을 만들 수 있는 결과를 반환합니다.
