from datetime import datetime, timedelta
from math import asin, ceil, cos, radians, sin, sqrt

from app.domain import ProviderLeg, ProviderRoute, ProviderWalkStep
from app.models import LegMode, PlaceInput, RouteMode, RouteSearchRequest, TimeSource


class MockRouteProvider:
    async def search(self, request: RouteSearchRequest) -> list[ProviderRoute]:
        distance = max(100, round(self._distance_m(request.origin, request.destination)))
        departure = request.departure_at or datetime.now().astimezone()
        if request.mode == RouteMode.WALK:
            return [self._walk(request.origin, request.destination, distance)]
        if request.mode == RouteMode.TAXI:
            return [self._taxi(request.origin, request.destination, distance)]
        return [self._transit(request.origin, request.destination, distance, departure)]

    def _walk(self, origin: PlaceInput, destination: PlaceInput, distance: int) -> ProviderRoute:
        duration = ceil(distance / 1.3)
        geometry = self._line(origin, destination)
        leg = ProviderLeg(
            provider_leg_id="mock_walk_leg_1",
            mode=LegMode.WALK,
            start=origin,
            end=destination,
            distance_m=distance,
            duration_sec=duration,
            geometry=geometry,
            steps=[
                ProviderWalkStep(
                    instruction=f"{destination.name}까지 보행로를 따라 이동하세요.",
                    distance_m=distance,
                    geometry=geometry,
                )
            ],
        )
        return ProviderRoute(
            provider_route_id="mock_walk_1",
            mode=RouteMode.WALK,
            title="계단을 피하는 도보 경로",
            standard_duration_sec=duration,
            total_distance_m=distance,
            walk_distance_m=distance,
            transfer_count=0,
            fare_krw=0,
            legs=[leg],
        )

    def _taxi(self, origin: PlaceInput, destination: PlaceInput, distance: int) -> ProviderRoute:
        road_distance = round(distance * 1.25)
        duration = ceil(road_distance / 6.5)
        fare = max(4800, round((4800 + road_distance * 0.9) / 100) * 100)
        leg = ProviderLeg(
            provider_leg_id="mock_taxi_leg_1",
            mode=LegMode.TAXI,
            start=origin,
            end=destination,
            distance_m=road_distance,
            duration_sec=duration,
            geometry=self._line(origin, destination),
            expected_fare_krw=fare,
        )
        return ProviderRoute(
            provider_route_id="mock_taxi_1",
            mode=RouteMode.TAXI,
            title="택시 예상 경로",
            standard_duration_sec=duration,
            total_distance_m=road_distance,
            walk_distance_m=0,
            transfer_count=0,
            fare_krw=fare,
            legs=[leg],
        )

    def _transit(
        self,
        origin: PlaceInput,
        destination: PlaceInput,
        distance: int,
        departure: datetime,
    ) -> ProviderRoute:
        first = self._intermediate(origin, destination, 0.08, "출발역")
        last = self._intermediate(origin, destination, 0.92, "도착역")
        walk_distance = min(500, max(200, round(distance * 0.08)))
        first_walk = walk_distance // 2
        last_walk = walk_distance - first_walk
        first_duration = ceil(first_walk / 1.3)
        last_duration = ceil(last_walk / 1.3)
        subway_distance = max(100, distance - walk_distance)
        subway_duration = max(300, ceil(subway_distance / 9))
        board_at = departure + timedelta(seconds=first_duration + 180)
        alight_at = board_at + timedelta(seconds=subway_duration)
        legs = [
            ProviderLeg(
                provider_leg_id="mock_transit_walk_1",
                mode=LegMode.WALK,
                start=origin,
                end=first,
                distance_m=first_walk,
                duration_sec=first_duration,
                geometry=self._line(origin, first),
            ),
            ProviderLeg(
                provider_leg_id="mock_transit_subway_1",
                mode=LegMode.SUBWAY,
                start=first,
                end=last,
                distance_m=subway_distance,
                duration_sec=subway_duration,
                geometry=self._line(first, last),
                line_id="SUBWAY_LINE_2",
                line_name="2호선",
                line_color="#00A84D",
                departure_at=board_at,
                arrival_at=alight_at,
                time_source=TimeSource.SCHEDULED,
            ),
            ProviderLeg(
                provider_leg_id="mock_transit_walk_2",
                mode=LegMode.WALK,
                start=last,
                end=destination,
                distance_m=last_walk,
                duration_sec=last_duration,
                geometry=self._line(last, destination),
            ),
        ]
        total = first_duration + 180 + subway_duration + last_duration
        return ProviderRoute(
            provider_route_id="mock_transit_1",
            mode=RouteMode.TRANSIT,
            title="2호선, 엘리베이터 이용",
            standard_duration_sec=total,
            total_distance_m=distance,
            walk_distance_m=walk_distance,
            transfer_count=0,
            fare_krw=1500,
            legs=legs,
        )

    @staticmethod
    def _line(start: PlaceInput, end: PlaceInput) -> list[list[float]]:
        return [
            [start.coordinate.longitude, start.coordinate.latitude],
            [end.coordinate.longitude, end.coordinate.latitude],
        ]

    @staticmethod
    def _intermediate(
        origin: PlaceInput, destination: PlaceInput, ratio: float, name: str
    ) -> PlaceInput:
        return PlaceInput(
            name=name,
            coordinate={
                "latitude": origin.coordinate.latitude
                + (destination.coordinate.latitude - origin.coordinate.latitude) * ratio,
                "longitude": origin.coordinate.longitude
                + (destination.coordinate.longitude - origin.coordinate.longitude) * ratio,
            },
        )

    @staticmethod
    def _distance_m(origin: PlaceInput, destination: PlaceInput) -> float:
        latitude_1 = radians(origin.coordinate.latitude)
        latitude_2 = radians(destination.coordinate.latitude)
        delta_latitude = latitude_2 - latitude_1
        delta_longitude = radians(
            destination.coordinate.longitude - origin.coordinate.longitude
        )
        value = sin(delta_latitude / 2) ** 2 + (
            cos(latitude_1) * cos(latitude_2) * sin(delta_longitude / 2) ** 2
        )
        return 2 * 6_371_000 * asin(sqrt(value))
