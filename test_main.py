from datetime import datetime, timezone
from unittest.mock import Mock

import requests

import main
from main import create_weather_update_embed, fetch_weather, format_event_time

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


def _forecast(dt, description="Clear", icon="01d", temp=20.0, feels_like=19.0,
              humidity=50, wind_speed=5.0, pop=0.4):
    return {
        "dt": dt,
        "weather": [{"description": description, "icon": icon}],
        "main": {"temp": temp, "feels_like": feels_like, "humidity": humidity},
        "wind": {"speed": wind_speed},
        "pop": pop,
    }


def test_fetch_weather_without_api_key(monkeypatch):
    monkeypatch.setattr(main, "WEATHER_API_KEY", None)
    event_dt = datetime(2024, 3, 2, 15, 0, 0, tzinfo=timezone.utc)
    weather_string, pop = fetch_weather(50.4, 5.9, event_dt)
    assert weather_string == "Weather N/A (No API Key)"
    assert pop == 0


def test_fetch_weather_picks_closest_forecast(monkeypatch):
    monkeypatch.setattr(main, "WEATHER_API_KEY", "fake-key")
    event_dt = datetime(2024, 3, 2, 15, 0, 0, tzinfo=timezone.utc)
    event_ts = int(event_dt.timestamp())

    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {
        "list": [
            _forecast(event_ts - 3 * 3600, description="Cloudy", pop=0.1),
            _forecast(event_ts + 1800, description="Light Rain", icon="10d", pop=0.6),
            _forecast(event_ts + 3 * 3600, description="Clear", pop=0.0),
        ]
    }
    monkeypatch.setattr(main.requests, "get", Mock(return_value=response))

    weather_string, pop = fetch_weather(50.4, 5.9, event_dt)
    assert "Light Rain" in weather_string
    assert pop == 60.0


def test_fetch_weather_no_matching_forecast(monkeypatch):
    monkeypatch.setattr(main, "WEATHER_API_KEY", "fake-key")
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {"list": []}
    monkeypatch.setattr(main.requests, "get", Mock(return_value=response))

    event_dt = datetime(2024, 3, 2, 15, 0, 0, tzinfo=timezone.utc)
    weather_string, pop = fetch_weather(50.4, 5.9, event_dt)
    assert weather_string == "Weather forecast not available for this time."
    assert pop == 0


def test_fetch_weather_request_exception(monkeypatch):
    monkeypatch.setattr(main, "WEATHER_API_KEY", "fake-key")
    monkeypatch.setattr(
        main.requests, "get", Mock(side_effect=requests.exceptions.ConnectionError())
    )

    event_dt = datetime(2024, 3, 2, 15, 0, 0, tzinfo=timezone.utc)
    weather_string, pop = fetch_weather(50.4, 5.9, event_dt)
    assert weather_string == "Weather fetch failed"
    assert pop == 0
