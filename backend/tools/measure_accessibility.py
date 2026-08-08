"""접근성 조회가 외부를 몇 번, 얼마나 오래 기다리는지 잰다.

바뀐 단위를 그대로 잰다. API를 통해 재지 않는 이유는 목 경로 제공자가 지하철 구간을
하나만 만들어서, 정작 문제였던 "구간이 늘수록 쌓이는 대기"가 드러나지 않기 때문이다.

외부 응답 시간은 **주입한 고정 지연**이다. 실제 API 응답 분포가 아니다.
여기서 확인하는 것은 호출 구조이지 실제 응답 시간이 아니다.

사용:
    uv run python tools/measure_accessibility.py            # 표로 출력
    uv run python tools/measure_accessibility.py --json     # 기계가 읽을 형태
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import datetime
from time import monotonic
from zoneinfo import ZoneInfo

from app.domain import ProviderLeg, ProviderRoute
from app.models import (
    Coordinate,
    DataConfidence,
    FacilityStatus,
    LegMode,
    PlaceInput,
    RouteMode,
)
from app.providers.accessibility import HybridAccessibilityProvider
from app.providers.seoul import SeoulElevator

SEOUL = ZoneInfo("Asia/Seoul")


class CountingSeoulClient:
    """호출 하나마다 정해진 시간을 쓰고, 몇 번 불렸는지 센다."""

    def __init__(self, delay_sec: float) -> None:
        self.delay_sec = delay_sec
        self.calls = 0

    async def get_elevator(self, _station_name: str):
        self.calls += 1
        await asyncio.sleep(self.delay_sec)
        return SeoulElevator(
            status=FacilityStatus.AVAILABLE,
            location_description="엘리베이터",
            confidence=DataConfidence.VERIFIED,
        )

    async def get_station_elevators(self, _station_name: str):
        self.calls += 1
        await asyncio.sleep(self.delay_sec)
        return []

    async def get_subway_arrivals(self, _station_name: str, _line_name: str):
        self.calls += 1
        await asyncio.sleep(self.delay_sec)
        return []


def _place(name: str, index: int) -> PlaceInput:
    return PlaceInput(
        name=name,
        coordinate=Coordinate(latitude=37.5 + index / 100, longitude=127.0 + index / 100),
    )


def _route(leg_count: int) -> ProviderRoute:
    """환승 n회 = 지하철 구간 n+1개."""
    legs = [
        ProviderLeg(
            provider_leg_id=f"leg-{i}",
            mode=LegMode.SUBWAY,
            start=_place(f"역{i}", i),
            end=_place(f"역{i + 1}", i + 1),
            distance_m=3000,
            duration_sec=600,
            geometry=[[127.0 + i / 100, 37.5 + i / 100], [127.0 + (i + 1) / 100, 37.5 + (i + 1) / 100]],
            line_id="SUBWAY_LINE_1",
            line_name="1호선",
            departure_at=datetime(2026, 7, 15, 14, 0, tzinfo=SEOUL),
            arrival_at=datetime(2026, 7, 15, 14, 10, tzinfo=SEOUL),
        )
        for i in range(leg_count)
    ]
    return ProviderRoute(
        provider_route_id="route",
        mode=RouteMode.TRANSIT,
        title="지하철 경로",
        standard_duration_sec=600 * leg_count,
        total_distance_m=3000 * leg_count,
        walk_distance_m=0,
        transfer_count=max(0, leg_count - 1),
        fare_krw=1500,
        legs=legs,
    )


async def _once(leg_count: int, candidates: int, delay_sec: float) -> tuple[float, int]:
    seoul = CountingSeoulClient(delay_sec)
    provider = HybridAccessibilityProvider(seoul)
    routes = [_route(leg_count) for _ in range(candidates)]
    started = monotonic()
    await provider.get_context(routes)
    return monotonic() - started, seoul.calls


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay-ms", type=float, default=50.0)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    delay = args.delay_ms / 1000
    # (지하철 구간 수, 경로 후보 수) — 환승 0·1·3회, 후보 1개와 3개
    cases = [(1, 1), (2, 1), (4, 1), (4, 3)]
    rows = []
    for leg_count, candidates in cases:
        samples = [await _once(leg_count, candidates, delay) for _ in range(args.repeat)]
        elapsed = [round(s[0] * 1000, 1) for s in samples]
        rows.append(
            {
                "subwayLegs": leg_count,
                "routeCandidates": candidates,
                "externalCalls": samples[0][1],
                "elapsedMsMedian": round(statistics.median(elapsed), 1),
                "elapsedMs": elapsed,
            }
        )

    result = {
        "injectedDelayMs": args.delay_ms,
        "repeat": args.repeat,
        "note": "외부 지연은 주입값이다. 실제 API 응답 분포가 아니다.",
        "cases": rows,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"주입 지연 {args.delay_ms}ms · {args.repeat}회 반복")
    print(f"{'지하철 구간':>10}{'경로 후보':>9}{'외부 호출':>9}{'대기(중앙값)':>13}")
    for row in rows:
        print(
            f"{row['subwayLegs']:>10}{row['routeCandidates']:>9}"
            f"{row['externalCalls']:>9}{row['elapsedMsMedian']:>11}ms"
        )


if __name__ == "__main__":
    asyncio.run(main())
