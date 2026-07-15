from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import MobilityAid, TravelerType, UpdateProfileRequest, UserProfile

SEOUL = ZoneInfo("Asia/Seoul")


def calculate_profile_default_speed(request: UpdateProfileRequest) -> float:
    speed = 1.0
    aid_speeds = {
        MobilityAid.MANUAL_WHEELCHAIR: 0.70,
        MobilityAid.POWER_WHEELCHAIR: 0.75,
        MobilityAid.STROLLER: 0.85,
        MobilityAid.CANE: 0.80,
        MobilityAid.CRUTCHES: 0.75,
        MobilityAid.WALKER: 0.72,
    }
    traveler_speeds = {
        TravelerType.SENIOR: 0.85,
        TravelerType.PREGNANT: 0.90,
        TravelerType.TEMPORARILY_INJURED: 0.80,
        TravelerType.MOBILITY_IMPAIRED: 0.70,
    }
    for aid in request.mobility_aids:
        speed = min(speed, aid_speeds[aid])
    for traveler_type in request.traveler_types:
        if traveler_type in traveler_speeds:
            speed = min(speed, traveler_speeds[traveler_type])
    return round(speed, 2)


class DemoProfileStore:
    def __init__(self, profile: UserProfile) -> None:
        self._profile = profile.model_copy(deep=True)

    def get(self) -> UserProfile:
        return self._profile.model_copy(deep=True)

    def replace(self, request: UpdateProfileRequest) -> UserProfile:
        movement_traits_changed = (
            self._profile.traveler_types != list(request.traveler_types)
            or self._profile.mobility_aids != list(request.mobility_aids)
        )
        walking_speed = self._profile.walking_speed.model_copy(deep=True)
        if movement_traits_changed:
            walking_speed = walking_speed.model_copy(
                update={
                    "walking_speed_mps": calculate_profile_default_speed(request),
                    "walking_speed_source": "PROFILE_DEFAULT",
                    "walking_speed_sample_count": 0,
                    "updated_at": datetime.now(SEOUL),
                }
            )
        self._profile = self._profile.model_copy(
            update={
                "traveler_types": list(request.traveler_types),
                "mobility_aids": list(request.mobility_aids),
                "preferences": request.preferences.model_copy(deep=True),
                "walking_speed": walking_speed,
            },
            deep=True,
        )
        return self.get()

    def learn_walking_speed(
        self,
        base_speed_mps: float,
        max_speed_mps: float,
        sample_count: int,
    ) -> UserProfile:
        """센서(안내 중 GPS)로 측정한 기본·최고 보행속도를 프로필에 반영한다."""
        walking_speed = self._profile.walking_speed.model_copy(
            update={
                "walking_speed_mps": base_speed_mps,
                "walking_speed_source": "LEARNED",
                "walking_speed_sample_count": sample_count,
                "updated_at": datetime.now(SEOUL),
                "base_speed_mps": base_speed_mps,
                "max_speed_mps": max_speed_mps,
            }
        )
        self._profile = self._profile.model_copy(
            update={"walking_speed": walking_speed}, deep=True
        )
        return self.get()
