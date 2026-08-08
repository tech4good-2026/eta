# 접근성 조회 — 차례로 묻던 것을 같이 묻는다

경로 하나에 접근성 정보를 붙일 때, 구간마다 외부를 **차례로** 물었다.
구간끼리는 서로 필요로 하는 게 없는데도 그랬다. 그래서 응답 시간이 호출들의 **합**이 됐다.

## 무엇이 문제였나

`backend/app/providers/accessibility.py`의 `get_context`가 경로 후보마다, 그 안의 구간마다
`await`했다. 지하철 구간 **하나**가 서로 무관한 호출 5개를 또 차례로 기다렸다.

```python
boarding  = await self.seoul.get_elevator(boarding_station)
alighting = await self.seoul.get_elevator(alighting_station)   # 앞과 무관한데 기다린다
boarding_units  = await self._station_units(boarding_station)
alighting_units = await self._station_units(alighting_station)
departures      = await self._subway_departures(boarding_station, line_name)
```

저장소 전체에 동시 실행 수단이 하나도 없었다 —
`asyncio.gather` 0 · `TaskGroup` 0 · `create_task` 0 · `asyncio.wait` 0 · `as_completed` 0.

## 무엇을 했나

1. **같이 묻는다** — 구간별·구간 안의 독립 호출을 `asyncio.gather`로 묶었다
2. **한 번만 묻는다** — 같은 역·같은 정류장이 여러 경로 후보에 겹쳐 나오면 한 번만 묻고 나눠 쓴다
3. **늦으면 기다리지 않는다** — provider마다 시간 한도(기본 3초)를 두고, 넘기면 그 항목만
   `UNKNOWN`으로 내려간다. 이 서비스에서 늦은 안내는 틀린 안내와 같다

3번은 새 사상이 아니다. 이 저장소는 원래 확인 못 한 정보를 '있음'으로 채우지 않고
`UNKNOWN`으로 그대로 응답한다. **늦은 것과 못 받은 것을 같게 다룬 것**이다.

## 어떻게 쟀나

| 항목 | 값 |
| --- | --- |
| before | `8102b7b` (`docs: clarify team roles`) |
| after | 같은 커밋에 위 변경만 얹은 상태 |
| 측정일 | 2026-08-08 |
| 호스트 | Apple M4 · macOS 26.3.1 |
| Python | 3.12.13 |
| 도구 | `backend/tools/measure_accessibility.py` (저장소에 포함) |
| 주입 지연 | 외부 호출 1건당 **50ms 고정** |
| 반복 | 케이스마다 5회, 중앙값 |

```bash
cd backend
PYTHONPATH=. uv run python tools/measure_accessibility.py
```

**API를 통해 재지 않았다.** 목 경로 제공자가 지하철 구간을 하나만 만들어서, 정작 문제였던
"구간이 늘수록 쌓이는 대기"가 API 경로에서는 드러나지 않는다. 그래서 바뀐 단위인
`get_context`를 직접 쟀다. before와 after는 **같은 스크립트**로 잰 값이다.

## 결과

| 지하철 구간 | 경로 후보 | 외부 호출 | | 대기 (중앙값) | |
| ---: | ---: | ---: | ---: | ---: | ---: |
| | | before | after | before | after |
| 1 | 1 | 5 | 5 | 258.0ms | **52.3ms** |
| 2 | 1 | 10 | 10 | 514.9ms | **52.5ms** |
| 4 | 1 | 20 | 20 | 1,031.2ms | **52.5ms** |
| 4 | 3 | 60 | **20** | 3,097.4ms | **51.9ms** |

읽는 법 —

- **대기가 구간 수에 비례해 늘던 것이 구간 수와 무관해졌다.** 구간 1개든 4개든 52ms다.
  주입 지연이 50ms이므로 이건 "한 번 기다린 시간"이다
- **경로 후보가 3개면 외부 호출이 60회였다.** 후보들이 같은 역을 공유하는데도 매번 물었다.
  이제 20회다
- 후보 1개 기준 외부 호출 수는 그대로다. 줄인 것은 **기다리는 순서**이지 호출 자체가 아니다

## 주장하지 않는 것

**외부 응답 시간은 주입한 50ms 고정값이다. 실제 TMAP·서울 공공데이터의 응답 분포가 아니다.**
여기서 확인한 것은 **호출 구조**다 — 기다림이 쌓이는가, 쌓이지 않는가. 실제 서비스의
응답 시간을 주장하는 수치가 아니다.

같은 이유로 이 수치를 처리량(RPS)이나 동시 사용자 지표로 쓰지 않는다. 단일 호출 경로를
한 번에 하나씩 잰 값이다.

`_get_elevator_rows`는 600초 캐시라 실제 운영에서는 엘리베이터 조회 상당수가 네트워크를
타지 않는다. 위 측정은 캐시가 없는 상태를 가정한 값이므로 실제 개선폭과 다를 수 있다.

## 함께 고정한 것

`backend/tests/test_accessibility_provider.py`

- 구간 4개짜리 경로에서 대기가 쌓이지 않는다
- 경로 후보 3개가 같은 구간을 공유하면 한 번만 묻는다
- 영영 답하지 않는 외부가 있어도 응답이 붙들리지 않고 `UNKNOWN`으로 내려간다

세 테스트 모두 `8102b7b`에서는 실패한다.
