"""보행 세그먼트 접근성 데이터 소스(서울 한정).

경로 난이도(경사·노면·폭·턱낮춤·점자블록·통행가능)를 세그먼트 단위로 제공하는
어댑터 자리다. 개인화 엔진은 이 값을 받아 도보 ETA에 환경 패널티를 반영한다.

실데이터 매핑(실제 어댑터 구현 시):

| 필드 | 출처 |
|------|------|
| ``surface_type``, ``width_m`` | 서울시 보도통계자료(OA-22240) — 포장재·보도 폭 |
| ``max_slope_percent`` | 서울시 경사도 표고·등고선(OA-22241) 계산값 |
| ``curb_ramp_present``, ``tactile_paving_present`` | 서울시 횡단보도 데이터 — 보도턱낮춤·점자블록 |
| ``passable`` | 도로시설(인도) 레이어 + 실시간 통제 |

원본 데이터셋을 확보하기 전까지는 값을 지어내지 않고 ``UnknownWalkwaySource``가
모두 UNKNOWN을 반환한다. 실제 데이터를 확보하면 동일한 ``WalkwaySource``
프로토콜을 구현해 ``build_container()``에서 주입만 교체하면 된다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from app.models import DataConfidence, DataSource, PlaceInput, SurfaceType


@dataclass(frozen=True)
class WalkwaySegment:
    has_stairs: bool | None = None
    max_slope_percent: float | None = None
    surface_type: SurfaceType | None = None
    width_m: float | None = None
    curb_ramp_present: bool | None = None
    tactile_paving_present: bool | None = None
    passable: bool = True
    confidence: DataConfidence = DataConfidence.UNKNOWN
    source: DataSource = DataSource.UNKNOWN


class WalkwaySource(Protocol):
    def segment_for(
        self, leg_id: str, start: PlaceInput, end: PlaceInput
    ) -> WalkwaySegment: ...


class UnknownWalkwaySource:
    """실데이터 미확보 상태의 정직한 기본값. 값을 지어내지 않고 UNKNOWN을 반환한다."""

    def segment_for(
        self, leg_id: str, start: PlaceInput, end: PlaceInput
    ) -> WalkwaySegment:
        return WalkwaySegment()


class MockWalkwaySource:
    """데모용 목업 세그먼트. 결정론적(동일 입력 → 동일 출력)이며 반드시
    SYNTHETIC_FIXTURE로 표시되어 실측 데이터와 구분된다. 실제 서울 데이터
    (OA-22240/22241) 어댑터가 준비되면 교체한다."""

    def segment_for(
        self, leg_id: str, start: PlaceInput, end: PlaceInput
    ) -> WalkwaySegment:
        seed = self._seed(leg_id, start, end)
        # 경사 0~5%: 급경사 하드 차단(6%) 아래에서 시간 패널티만 유발한다.
        max_slope_percent = round(float(seed % 6), 1)
        surface_type = (
            SurfaceType.ASPHALT,
            SurfaceType.BLOCK,
            SurfaceType.BLOCK,
            SurfaceType.CONCRETE,
            SurfaceType.STONE,
            SurfaceType.BRICK,
        )[seed % 6]
        width_m = round(0.9 + (seed % 17) * 0.1, 1)
        return WalkwaySegment(
            has_stairs=False,
            max_slope_percent=max_slope_percent,
            surface_type=surface_type,
            width_m=width_m,
            curb_ramp_present=seed % 5 != 0,
            tactile_paving_present=seed % 3 != 0,
            passable=True,
            confidence=DataConfidence.ESTIMATED,
            source=DataSource.SYNTHETIC_FIXTURE,
        )

    @staticmethod
    def _seed(leg_id: str, start: PlaceInput, end: PlaceInput) -> int:
        key = (
            f"{leg_id}|{start.coordinate.latitude:.4f},{start.coordinate.longitude:.4f}"
            f"|{end.coordinate.latitude:.4f},{end.coordinate.longitude:.4f}"
        )
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return int(digest[:8], 16)
