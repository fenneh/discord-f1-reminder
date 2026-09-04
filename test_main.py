from datetime import datetime, timezone

from main import create_weather_update_embed, format_event_time

RACE_INFO = {
    "date": "2024-03-02",
    "time": "15:00:00Z",
    "Qualifying": {"date": "2024-03-01", "time": "12:00:00Z"},
    "Sprint": {"date": "2024-03-01", "time": "08:00:00Z"},
    "FirstPractice": {"date": "2024-02-29", "time": "11:30:00Z"},
    "SecondPractice": {"date": "2024-02-29", "time": "15:00:00Z"},
    "ThirdPractice": {"date": "2024-03-01", "time": "11:30:00Z"},
}

RACE_INFO_WITH_CIRCUIT = {
    **RACE_INFO,
    "raceName": "Test Grand Prix",
    "season": "2024",
    "Circuit": {"Location": {"lat": "50.4372", "long": "5.9714"}},
}


def test_race_event():
    s, dt = format_event_time(RACE_INFO, "Race")
    assert dt == datetime(2024, 3, 2, 15, 0, 0, tzinfo=timezone.utc)
    assert "2024" in s


def test_qualifying_event():
    s, dt = format_event_time(RACE_INFO, "Qualifying")
    assert dt == datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert s is not None


def test_sprint_event():
    s, dt = format_event_time(RACE_INFO, "Sprint")
    assert dt == datetime(2024, 3, 1, 8, 0, 0, tzinfo=timezone.utc)


def test_first_practice():
    s, dt = format_event_time(RACE_INFO, "FirstPractice")
    assert dt == datetime(2024, 2, 29, 11, 30, 0, tzinfo=timezone.utc)


def test_missing_event_type():
    s, dt = format_event_time({"date": "2024-03-02", "time": "15:00:00Z"}, "Sprint")
    assert s is None
    assert dt is None


def test_missing_time():
    s, dt = format_event_time({"date": "2024-03-02"}, "Race")
    assert s is None
    assert dt is None


def test_time_without_z_suffix():
    race_info = {"date": "2024-03-02", "time": "15:00:00"}
    s, dt = format_event_time(race_info, "Race")
    assert dt == datetime(2024, 3, 2, 15, 0, 0, tzinfo=timezone.utc)


def test_weather_update_embed_content():
    event_dt = datetime(2024, 3, 2, 15, 0, 0, tzinfo=timezone.utc)
    embed = create_weather_update_embed(
        RACE_INFO_WITH_CIRCUIT, "Race", event_dt, 60.0, 20.0, "Cloudy"
    )
    assert "Test Grand Prix" in embed["title"]
    assert "Race" in embed["title"]
    assert "Cloudy" in embed["fields"][0]["value"]
    assert embed["fields"][1]["value"] == "Rain chance changed from 20% to **60%**."


def test_weather_update_embed_unknown_event_type_uses_default_emoji():
    event_dt = datetime(2024, 3, 2, 15, 0, 0, tzinfo=timezone.utc)
    embed = create_weather_update_embed(
        RACE_INFO_WITH_CIRCUIT, "Shakedown", event_dt, 10.0, 5.0, "Sunny"
    )
    assert embed["title"].startswith("🏁")
