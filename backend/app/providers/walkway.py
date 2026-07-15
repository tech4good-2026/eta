"""보행 세그먼트 접근성 데이터 소스.

경로 난이도(경사·노면·폭·턱낮춤·점자블록·통행가능)를 세그먼트 단위로 제공한다.
개인화 엔진은 이 값을 받아 도보 ETA에 환경 패널티를 반영한다.

실데이터 매핑(어댑터 구현 시):

| 필드 | 출처 |
|------|------|
| ``surface_type``, ``width_m`` | 서울시 보도통계자료(OA-22240) — 포장재·보도 폭 |
| ``max_slope_percent`` | 서울시 경사도 표고·등고선(OA-22241) 계산값 |
| ``curb_ramp_present``, ``tactile_paving_present`` | 전국 횡단보도 표준데이터 — 보도턱낮춤·점자블록 |
| ``passable`` | 행정안전부 생활안전지도 도로시설(인도) 레이어 + 실시간 통제 |

현재 환경에는 원본 데이터셋(shp/공공데이터 API)이 없어 ``SyntheticWalkwaySource``가
좌표 기반의 결정론적 합성값을 제공한다. 실제 어댑터는 동일한 ``WalkwaySource``
프로토콜을 구현해 ``build_container()``에서 주입만 교체하면 된다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from app.models import DataConfidence, DataSource, PlaceInput, SurfaceType


@dataclass(frozen=True)
class WalkwaySegment:
    has_stairs: bool = False
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


_ROUGH_SURFACES = (SurfaceType.BLOCK, SurfaceType.STONE, SurfaceType.BRICK)


class SyntheticWalkwaySource:
    """좌표로부터 결정론적 합성 세그먼트를 만든다(동일 입력 → 동일 출력)."""

    def segment_for(
        self, leg_id: str, start: PlaceInput, end: PlaceInput
    ) -> WalkwaySegment:
        seed = self._seed(leg_id, start, end)
        # 경사: 완만~약간 가파름(0~5%). 급경사 하드 차단(6%) 아래로 두어 합성값이
        # 경로를 임의로 UNAVAILABLE로 만들지 않게 하면서 시간 패널티는 유발한다.
        max_slope_percent = round(float(seed % 6), 1)
        # 노면: 서울 보도는 인터로킹 블록이 흔하고 일부는 석재/아스팔트.
        surface_type = (
            SurfaceType.ASPHALT,
            SurfaceType.BLOCK,
            SurfaceType.BLOCK,
            SurfaceType.CONCRETE,
            SurfaceType.STONE,
            SurfaceType.BRICK,
        )[seed % 6]
        # 보도 폭: 0.9~2.5m 사이.
        width_m = round(0.9 + (seed % 17) * 0.1, 1)
        # 횡단보도 턱낮춤/점자블록: 대체로 있으나 일부 미비.
        curb_ramp_present = seed % 5 != 0
        tactile_paving_present = seed % 3 != 0
        return WalkwaySegment(
            has_stairs=False,
            max_slope_percent=max_slope_percent,
            surface_type=surface_type,
            width_m=width_m,
            curb_ramp_present=curb_ramp_present,
            tactile_paving_present=tactile_paving_present,
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
