from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from statistics import median
from uuid import uuid4

from app.errors import ApiError
from app.models import (
    CompleteNavigationRequest,
    Coordinate,
    GuidanceInstruction,
    LegMode,
    LocationSample,
    NavigationCompletion,
    NavigationSession,
    NavigationStatus,
    NavigationUpdate,
    PlaceInput,
    RerouteReason,
    RerouteRequest,
    RerouteSuggestion,
    RouteLeg,
    RouteSearchRequest,
    UserProfile,
)
from app.profile import DemoProfileStore
from app.providers.seoul import SeoulDataClient
from app.services import RouteService
from app.storage import MemoryTTLStore, StoreState


@dataclass
class NavigationState:
    session: NavigationSession
    route_request: RouteSearchRequest
    last_processed_at: datetime | None = None
    off_route_sample_count: int = 0
    missed_transit_sample_count: int = 0
    walk_speed_samples: list[float] = field(default_factory=list)
    last_walk_sample: tuple[Coordinate, datetime, float] | None = None


class NavigationService:
    min_position_interval_sec = 5
    off_route_threshold_m = 60
    boarding_geofence_m = 150
    missed_departure_grace_sec = 60
    consecutive_samples_required = 2

    # 안내 중 도보 속도 표본 수집 조건.
    walk_speed_min_mps = 0.15
    walk_speed_max_mps = 2.5
    walk_speed_accuracy_limit_m = 30.0
    walk_speed_min_interval_sec = 2.0
    walk_speed_max_interval_sec = 120.0
    min_walk_speed_samples = 3

    def __init__(
        self,
        route_service: RouteService,
        store: MemoryTTLStore[NavigationState],
        ttl_sec: int = 7200,
        clock: Callable[[], datetime] | None = None,
        seoul: SeoulDataClient | None = None,
        profile_store: DemoProfileStore | None = None,
    ) -> None:
        self.route_service = route_service
        self.store = store
        self.ttl_sec = ttl_sec
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.seoul = seoul
        self.profile_store = profile_store

    def start(self, route_id: str) -> NavigationSession:
        stored = self.route_service.get_stored_route(route_id)
        now = self.clock()
        session = NavigationSession(
            session_id=f"nav_{uuid4().hex}",
            status=NavigationStatus.ACTIVE,
            route_revision=1,
            route=stored.route,
            started_at=now,
            updated_at=now,
            next_instruction=self._next_instruction(stored.route.legs[0]),
        )
        self.store.put(
            session.session_id,
            NavigationState(session=session, route_request=stored.request),
            self.ttl_sec,
        )
        return session

    async def update_position(
        self, session_id: str, sample: LocationSample
    ) -> NavigationUpdate:
        state = self._get_state(session_id)
        if state.last_processed_at is not None:
            elapsed = (sample.recorded_at - state.last_processed_at).total_seconds()
            if elapsed < self.min_position_interval_sec:
                return self._as_update(state.session)

        state.last_processed_at = sample.recorded_at
        self._collect_walk_speed(state, sample)
        transit_leg = self._next_transit_leg(state.session.route.legs)
        missed = False
        if transit_leg is not None and transit_leg.departure_at is not None:
            near_boarding = (
                self._distance_m(sample.coordinate, transit_leg.start.coordinate)
                <= self.boarding_geofence_m + sample.accuracy_m
            )
            departure_passed = sample.recorded_at >= transit_leg.departure_at + timedelta(
                seconds=self.missed_departure_grace_sec
            )
            missed = near_boarding and departure_passed

        if missed:
            state.missed_transit_sample_count += 1
        else:
            state.missed_transit_sample_count = 0

        distance_to_route = self._distance_to_route_m(
            sample.coordinate, state.session.route.legs
        )
        off_route = distance_to_route > self.off_route_threshold_m + sample.accuracy_m
        if off_route:
            state.off_route_sample_count += 1
        else:
            state.off_route_sample_count = 0

        suggestion = None
        if state.missed_transit_sample_count >= self.consecutive_samples_required:
            message = "대중교통을 놓친 것 같아요. 현재 위치에서 다시 찾을까요?"
            if self.seoul is not None and transit_leg is not None:
                try:
                    next_arrival = await self.seoul.get_next_arrival_sec(transit_leg.start.name)
                except ApiError:
                    next_arrival = None
                if next_arrival is not None:
                    minutes = max(1, round(next_arrival / 60))
                    message = f"대중교통을 놓친 것 같아요. 다음 도착은 약 {minutes}분 후입니다."
            suggestion = RerouteSuggestion(
                reason=RerouteReason.MISSED_TRANSIT,
                message=message,
                detected_at=sample.recorded_at,
            )
        elif state.off_route_sample_count >= self.consecutive_samples_required:
            suggestion = RerouteSuggestion(
                reason=RerouteReason.OFF_ROUTE,
                message="경로에서 벗어난 것 같아요. 현재 위치에서 다시 찾을까요?",
                detected_at=sample.recorded_at,
            )

        status = (
            NavigationStatus.REROUTE_SUGGESTED
            if suggestion is not None
            else NavigationStatus.ACTIVE
        )
        state.session = state.session.model_copy(
            update={
                "status": status,
                "updated_at": sample.recorded_at,
                "reroute_suggestion": suggestion,
            }
        )
        self.store.put(session_id, state, self.ttl_sec)
        return self._as_update(state.session)

    async def reroute(
        self,
        session_id: str,
        request: RerouteRequest,
        profile: UserProfile,
    ) -> NavigationSession:
        state = self._get_state(session_id)
        if request.current_station is not None:
            origin = request.current_station
        else:
            assert request.current_location is not None
            origin = PlaceInput(
                name="현재 위치",
                coordinate=request.current_location.coordinate,
            )
        recorded_at = (
            request.current_location.recorded_at
            if request.current_location is not None
            else self.clock()
        )
        route_request = RouteSearchRequest(
            origin=origin,
            destination=state.route_request.destination,
            mode=state.route_request.mode,
            departure_at=recorded_at,
        )
        searched = await self.route_service.search(route_request, profile)
        if not searched.routes:
            raise ApiError(
                422,
                "NO_ACCESSIBLE_ROUTE",
                "현재 위치에서 이용 가능한 경로를 찾지 못했습니다.",
                {"fallbackModes": searched.fallback_modes},
            )
        route = searched.routes[0]
        now = self.clock()
        state.session = NavigationSession(
            session_id=state.session.session_id,
            status=NavigationStatus.ACTIVE,
            route_revision=state.session.route_revision + 1,
            route=route,
            started_at=state.session.started_at,
            updated_at=now,
            next_instruction=self._next_instruction(route.legs[0]),
        )
        state.route_request = route_request
        state.last_processed_at = None
        state.off_route_sample_count = 0
        state.missed_transit_sample_count = 0
        state.last_walk_sample = None
        self.store.put(session_id, state, self.ttl_sec)
        return state.session

    def complete(
        self,
        session_id: str,
        request: CompleteNavigationRequest,
        profile: UserProfile,
    ) -> NavigationCompletion:
        state = self._get_state(session_id)
        if state.session.status == NavigationStatus.COMPLETED:
            raise ApiError(
                409,
                "SESSION_ALREADY_COMPLETED",
                "이미 완료된 안내 세션입니다.",
            )
        walking_speed = profile.walking_speed
        walking_speed_updated = False
        learned = self._learn_from_samples(state.walk_speed_samples)
        if learned is not None and self.profile_store is not None:
            base_speed, max_speed, sample_count = learned
            walking_speed = self.profile_store.learn_walking_speed(
                base_speed, max_speed, sample_count
            ).walking_speed
            walking_speed_updated = True
        state.session = state.session.model_copy(
            update={
                "status": NavigationStatus.COMPLETED,
                "updated_at": request.completed_at,
                "reroute_suggestion": None,
            }
        )
        self.store.put(session_id, state, self.ttl_sec)
        return NavigationCompletion(
            session_id=session_id,
            route_revision=state.session.route_revision,
            completed_at=request.completed_at,
            walking_speed_updated=walking_speed_updated,
            walking_speed=walking_speed,
        )

    def debug_state(self, session_id: str) -> NavigationState:
        return self._get_state(session_id)

    def _get_state(self, session_id: str) -> NavigationState:
        result = self.store.get(session_id)
        if result.state != StoreState.ACTIVE or result.value is None:
            raise ApiError(404, "SESSION_NOT_FOUND", "안내 세션을 찾을 수 없습니다.")
        return result.value

    @staticmethod
    def _as_update(session: NavigationSession) -> NavigationUpdate:
        return NavigationUpdate(
            session_id=session.session_id,
            status=session.status,
            route_revision=session.route_revision,
            updated_at=session.updated_at,
            next_instruction=session.next_instruction,
            reroute_suggestion=session.reroute_suggestion,
        )

    @staticmethod
    def _next_instruction(leg: RouteLeg) -> GuidanceInstruction:
        if leg.mode in {LegMode.BUS, LegMode.SUBWAY}:
            expected_at = leg.departure_at
            message = f"{getattr(leg, 'route_name', None) or getattr(leg, 'line_name', '대중교통')}에 탑승하세요."
            instruction_type = "BOARD"
        elif leg.mode == LegMode.WALK:
            expected_at = None
            message = leg.steps[0].instruction
            instruction_type = "WALK"
        else:
            expected_at = None
            message = "택시 예상 경로를 따라 이동하세요."
            instruction_type = "BOARD"
        return GuidanceInstruction(
            instruction_id=f"instruction_{uuid4().hex}",
            type=instruction_type,
            message=message,
            distance_to_action_m=leg.distance_m,
            expected_at=expected_at,
        )

    def _collect_walk_speed(
        self, state: NavigationState, sample: LocationSample
    ) -> None:
        """연속한 GPS 표본으로 도보 구간의 실제 이동속도를 계산해 누적한다.

        보행 구간(가장 가까운 leg가 WALK)일 때, 표본 정확도·간격·속도가 타당한
        경우만 수집한다. 차량 이동(속도 상한 초과)이나 정지는 자연히 걸러진다.
        """
        previous = state.last_walk_sample
        state.last_walk_sample = (
            sample.coordinate,
            sample.recorded_at,
            sample.accuracy_m,
        )
        if previous is None:
            return
        prev_coordinate, prev_time, prev_accuracy = previous
        elapsed = (sample.recorded_at - prev_time).total_seconds()
        if not (
            self.walk_speed_min_interval_sec
            <= elapsed
            <= self.walk_speed_max_interval_sec
        ):
            return
        if (
            sample.accuracy_m > self.walk_speed_accuracy_limit_m
            or prev_accuracy > self.walk_speed_accuracy_limit_m
        ):
            return
        if not self._on_walk_leg(sample.coordinate, state.session.route.legs):
            return
        speed = self._distance_m(prev_coordinate, sample.coordinate) / elapsed
        if self.walk_speed_min_mps <= speed <= self.walk_speed_max_mps:
            state.walk_speed_samples.append(speed)

    def _learn_from_samples(
        self, samples: list[float]
    ) -> tuple[float, float, int] | None:
        """표본에서 기본속도(중앙값)와 최고속도를 산출한다."""
        if len(samples) < self.min_walk_speed_samples:
            return None
        base_speed = round(min(max(median(samples), 0.1), 3.0), 2)
        max_speed = round(min(max(max(samples), base_speed), 3.0), 2)
        return base_speed, max_speed, len(samples)

    def _on_walk_leg(self, coordinate: Coordinate, legs: list[RouteLeg]) -> bool:
        leg = self._nearest_leg(coordinate, legs)
        return leg is not None and leg.mode == LegMode.WALK

    @classmethod
    def _nearest_leg(cls, coordinate: Coordinate, legs: list[RouteLeg]):
        best_leg = None
        best_distance = float("inf")
        for leg in legs:
            points = leg.geometry.coordinates
            for start, end in zip(points, points[1:], strict=False):
                distance = cls._point_to_segment_m(coordinate, start, end)
                if distance < best_distance:
                    best_distance = distance
                    best_leg = leg
        return best_leg

    @staticmethod
    def _next_transit_leg(legs: list[RouteLeg]):
        return next(
            (leg for leg in legs if leg.mode in {LegMode.BUS, LegMode.SUBWAY}),
            None,
        )

    @classmethod
    def _distance_to_route_m(cls, coordinate: Coordinate, legs: list[RouteLeg]) -> float:
        distances = []
        for leg in legs:
            points = leg.geometry.coordinates
            for start, end in zip(points, points[1:], strict=False):
                distances.append(cls._point_to_segment_m(coordinate, start, end))
        return min(distances) if distances else float("inf")

    @staticmethod
    def _point_to_segment_m(
        point: Coordinate, start: list[float], end: list[float]
    ) -> float:
        latitude_scale = 111_320.0
        longitude_scale = latitude_scale * cos(radians(point.latitude))
        start_x = (start[0] - point.longitude) * longitude_scale
        start_y = (start[1] - point.latitude) * latitude_scale
        end_x = (end[0] - point.longitude) * longitude_scale
        end_y = (end[1] - point.latitude) * latitude_scale
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        squared_length = delta_x * delta_x + delta_y * delta_y
        if squared_length == 0:
            return sqrt(start_x * start_x + start_y * start_y)
        projection = max(
            0.0,
            min(1.0, -(start_x * delta_x + start_y * delta_y) / squared_length),
        )
        closest_x = start_x + projection * delta_x
        closest_y = start_y + projection * delta_y
        return sqrt(closest_x * closest_x + closest_y * closest_y)

    @staticmethod
    def _distance_m(first: Coordinate, second: Coordinate) -> float:
        first_latitude = radians(first.latitude)
        second_latitude = radians(second.latitude)
        delta_latitude = second_latitude - first_latitude
        delta_longitude = radians(second.longitude - first.longitude)
        value = sin(delta_latitude / 2) ** 2 + (
            cos(first_latitude) * cos(second_latitude) * sin(delta_longitude / 2) ** 2
        )
        return 2 * 6_371_000 * asin(sqrt(value))
