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
