from datetime import datetime, timezone
from unittest.mock import Mock

import requests

import main
from main import (
    create_discord_embed,
    create_weather_update_embed,
    fetch_weather,
    format_event_time,
    schedule_event_notification,
)

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


def test_sprint_qualifying_event():
    race_info = {
        **RACE_INFO,
        "SprintQualifying": {"date": "2024-03-01", "time": "10:30:00Z"},
    }
    s, dt = format_event_time(race_info, "SprintQualifying")
    assert dt == datetime(2024, 3, 1, 10, 30, 0, tzinfo=timezone.utc)
    assert s is not None


def test_sprint_qualifying_notification_is_scheduled(monkeypatch):
    race_info = {
        "season": "2026",
        "round": "2",
        "raceName": "Test Grand Prix",
        "url": "https://example.com/race",
        "date": "2099-03-15",
        "time": "15:00:00Z",
        "SprintQualifying": {"date": "2099-03-13", "time": "12:00:00Z"},
        "Circuit": {
            "circuitId": "bahrain",
            "circuitName": "Test Circuit",
            "url": "https://example.com/circuit",
            "Location": {
                "lat": "26.0325",
                "long": "50.5106",
                "locality": "Sakhir",
                "country": "Bahrain",
            },
        },
    }
    create_embed = Mock()
    monkeypatch.setattr(main, "create_discord_embed", create_embed)
    scheduler = Mock()

    schedule_event_notification(scheduler, race_info, "SprintQualifying")

    notification_job = scheduler.add_job.call_args_list[0]
    assert notification_job.args[0] is main.send_event_notification
    assert notification_job.kwargs["id"] == "2026_2_SprintQualifying_notification"
    create_embed.assert_not_called()


def test_send_event_notification_stores_rain_chance(monkeypatch):
    event_dt = datetime(2099, 3, 13, 12, 0, 0, tzinfo=timezone.utc)
    race_info = {
        "raceName": "Test Grand Prix",
        "season": "2026",
        "round": "2",
        "Circuit": {"Location": {"lat": "26.0325", "long": "50.5106"}},
    }
    sent = []
    monkeypatch.setattr(main, "create_discord_embed", Mock(return_value=({"title": "test"}, "⏱️", 35.0)))
    monkeypatch.setattr(main, "send_discord_notification", sent.append)
    main.last_notified_pop.clear()

    main.send_event_notification(race_info, "SprintQualifying", "Fri, Mar 13, 2099 at 12:00 UTC", event_dt, "2026_2_SprintQualifying")

    assert sent == [{"title": "test"}]
    assert main.last_notified_pop["2026_2_SprintQualifying"] == 35.0


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


EMBED_RACE_INFO = {
    **RACE_INFO,
    "raceName": "Test Grand Prix",
    "url": "https://example.com/race",
    "season": "2024",
    "round": "1",
    "Circuit": {
        "circuitId": "spa",
        "circuitName": "Test Circuit",
        "url": "https://example.com/circuit",
        "Location": {
            "lat": "50.4372",
            "long": "5.9714",
            "locality": "Spa",
            "country": "Belgium",
        },
    },
}

EMBED_EVENT_DT = datetime(2024, 3, 2, 15, 0, 0, tzinfo=timezone.utc)


def test_create_discord_embed_builds_core_fields(monkeypatch):
    monkeypatch.setattr(main, "fetch_weather", Mock(return_value=("Sunny", 20.0)))

    embed, emoji, pop = create_discord_embed(
        EMBED_RACE_INFO, "Qualifying", "Fri, Mar 1, 2024 at 12:00 UTC", EMBED_EVENT_DT
    )

    fields = {field["name"]: field["value"] for field in embed["fields"]}
    assert "F1 Qualifying Reminder!" in embed["title"]
    assert "Test Grand Prix" in embed["description"]
    assert fields["Qualifying Start Time"].startswith("<t:")
    assert fields["Round"] == "1"
    assert "Test Circuit" in fields["Circuit"]
    assert fields["Location"] == "Spa, Belgium"
    assert "Sunny" in fields[":cloud: Weather Forecast"]
    assert "Rain Chance: 20%" in fields[":cloud: Weather Forecast"]
    assert embed["footer"]["text"] == f"{main.BOT_NAME} - Season 2024"
    assert emoji == main.EVENT_EMOJI_MAP["Qualifying"]
    assert pop == 20.0


def test_create_discord_embed_formats_ergast_grid(monkeypatch):
    monkeypatch.setattr(main, "fetch_weather", Mock(return_value=("Dry", 10.0)))
    monkeypatch.setattr(
        main,
        "fetch_starting_grid",
        Mock(
            return_value=[
                {"position": 1, "Driver": {"familyName": "Verstappen"}},
                {"position": 2, "Driver": {"familyName": "Norris"}},
                {"position": 3, "Driver": {"familyName": "Leclerc"}},
            ]
        ),
    )
    openf1 = Mock()
    monkeypatch.setattr(main, "fetch_starting_grid_openf1", openf1)

    embed, _, _ = create_discord_embed(EMBED_RACE_INFO, "Race", "Sat", EMBED_EVENT_DT)

    openf1.assert_not_called()
    grid_field = embed["fields"][-1]
    assert grid_field["name"].endswith("Starting Grid")
    assert grid_field["value"].startswith("```\n")
    assert "P1  Verstappen | P2  Norris" in grid_field["value"]
    assert "P3  Leclerc" in grid_field["value"]


def test_create_discord_embed_falls_back_to_openf1_grid(monkeypatch):
    monkeypatch.setattr(main, "fetch_weather", Mock(return_value=("Dry", 10.0)))
    monkeypatch.setattr(main, "fetch_starting_grid", Mock(return_value=None))
    openf1 = Mock(
        return_value=[
            {"position": 1, "Driver": {"familyName": "Verstappen"}},
            {"position": 10, "Driver": {"familyName": "Alonso"}},
        ]
    )
    monkeypatch.setattr(main, "fetch_starting_grid_openf1", openf1)

    embed, _, _ = create_discord_embed(EMBED_RACE_INFO, "Race", "Sat", EMBED_EVENT_DT)

    openf1.assert_called_once_with("2024", "spa")
    grid_field = embed["fields"][-1]
    assert grid_field["name"].endswith("Starting Grid")
    assert "P1  Verstappen | P10 Alonso" in grid_field["value"]


def test_create_discord_embed_omits_grid_when_unavailable(monkeypatch):
    monkeypatch.setattr(main, "fetch_weather", Mock(return_value=("Dry", 10.0)))
    monkeypatch.setattr(main, "fetch_starting_grid", Mock(return_value=None))
    monkeypatch.setattr(main, "fetch_starting_grid_openf1", Mock(return_value=None))

    embed, _, _ = create_discord_embed(EMBED_RACE_INFO, "Race", "Sat", EMBED_EVENT_DT)

    assert all(not field["name"].endswith("Starting Grid") for field in embed["fields"])


def test_create_discord_embed_skips_grid_for_practice(monkeypatch):
    monkeypatch.setattr(main, "fetch_weather", Mock(return_value=("Dry", 10.0)))
    fetch_grid = Mock()
    monkeypatch.setattr(main, "fetch_starting_grid", fetch_grid)

    embed, _, _ = create_discord_embed(
        EMBED_RACE_INFO, "FirstPractice", "Thu", EMBED_EVENT_DT
    )

    fetch_grid.assert_not_called()
    assert all(not field["name"].endswith("Starting Grid") for field in embed["fields"])
