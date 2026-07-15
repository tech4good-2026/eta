from app.main import demo_profile
from app.profile import DemoProfileStore


def test_learned_walking_speed_accumulates_across_sessions() -> None:
    store = DemoProfileStore(demo_profile())

    learned = store.learn_walking_speed(
        base_speed_mps=1.2,
        max_speed_mps=1.4,
        sample_count=4,
    )

    speed = learned.walking_speed
    assert speed.walking_speed_sample_count == 16
    assert speed.base_speed_mps == 0.9
    assert speed.walking_speed_mps == 0.9
    assert speed.max_speed_mps == 1.4
