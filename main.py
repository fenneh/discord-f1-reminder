# F1 Reminder Bot

import os
import requests
import json
import time
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
import argparse # Add argparse import

load_dotenv() # Load environment variables from .env file

DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
F1_API_URL = "https://api.jolpi.ca/ergast/f1/current.json" # Use current season
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY') # Add Weather API Key
WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/forecast"

# Load notification lead time from .env, default to 180 minutes (3 hours)
DEFAULT_LEAD_MINUTES = 180
try:
    NOTIFICATION_LEAD_MINUTES = int(os.getenv('NOTIFICATION_LEAD_MINUTES', DEFAULT_LEAD_MINUTES))
    if NOTIFICATION_LEAD_MINUTES < 0:
        print(f"Warning: NOTIFICATION_LEAD_MINUTES cannot be negative. Using default {DEFAULT_LEAD_MINUTES} minutes.")
        NOTIFICATION_LEAD_MINUTES = DEFAULT_LEAD_MINUTES
except (ValueError, TypeError):
    print(f"Warning: Invalid value for NOTIFICATION_LEAD_MINUTES. Using default {DEFAULT_LEAD_MINUTES} minutes.")
    NOTIFICATION_LEAD_MINUTES = DEFAULT_LEAD_MINUTES

# Load Bot Name from .env, default if missing
BOT_NAME = os.getenv('BOT_NAME', 'F1 Reminder Bot')

# Define event types in order of typical occurrence within a race weekend
EVENT_TYPES_ORDERED = ['FirstPractice', 'SecondPractice', 'ThirdPractice', 'Sprint', 'Qualifying', 'Race']


def fetch_schedule():
    """Fetches the current F1 season schedule."""
    try:
        response = requests.get(F1_API_URL)
        response.raise_for_status() # Raise an exception for bad status codes
        data = response.json()
        return data['MRData']['RaceTable']['Races']
    except requests.exceptions.RequestException as e:
        print(f"Error fetching F1 schedule: {e}")
        return None
    except json.JSONDecodeError:
        print("Error decoding JSON response from F1 API.")
        return None

def fetch_weather(lat, lon, event_dt_utc):
    """Fetches weather forecast for the given coordinates around the event time."""
    if not WEATHER_API_KEY:
        print("Weather API key not configured. Skipping weather fetch.")
        return "Weather N/A (No API Key)"

    try:
        params = {
            'lat': lat,
            'lon': lon,
            'appid': WEATHER_API_KEY,
            'units': 'metric' # Use metric units (Celsius)
        }
        response = requests.get(WEATHER_API_URL, params=params)
        response.raise_for_status()
        weather_data = response.json()

        # Find the forecast closest to the event time (within the 5-day/3-hour limit)
        closest_forecast = None
        min_time_diff = float('inf')
        event_timestamp = event_dt_utc.timestamp()

        for forecast in weather_data.get('list', []):
            forecast_timestamp = forecast['dt']
            time_diff = abs(event_timestamp - forecast_timestamp)
            if time_diff < min_time_diff:
                min_time_diff = time_diff
                closest_forecast = forecast

        if closest_forecast:
            weather_desc = closest_forecast['weather'][0]['description'].title()
            temp = closest_forecast['main']['temp']
            feels_like = closest_forecast['main']['feels_like']
            humidity = closest_forecast['main']['humidity']
            wind_speed = closest_forecast['wind']['speed'] # Meter/sec
            pop = closest_forecast.get('pop', 0) * 100 # Probability of precipitation

            # Convert wind speed to km/h
            wind_speed_kmh = wind_speed * 3.6

            # Get weather icon code - see https://openweathermap.org/weather-conditions#Weather-Condition-Codes-2
            icon_code = closest_forecast['weather'][0]['icon']
            # Map common icons to emojis (add more as needed)
            icon_map = {
                "01d": "☀️", "01n": "🌙", # clear sky
                "02d": "🌤️", "02n": "☁️", # few clouds
                "03d": "☁️", "03n": "☁️", # scattered clouds
                "04d": "☁️", "04n": "☁️", # broken clouds
                "09d": "🌧️", "09n": "🌧️", # shower rain
                "10d": "🌦️", "10n": "🌧️", # rain
                "11d": "⛈️", "11n": "⛈️", # thunderstorm
                "13d": "❄️", "13n": "❄️", # snow
                "50d": "🌫️", "50n": "🌫️", # mist
            }
            weather_icon = icon_map.get(icon_code, "")


            # Format the string nicely
            return (f"{weather_icon} {weather_desc}\n" # Weather description
                    f"🌡️ Temp: {temp:.1f}°C (Feels like: {feels_like:.1f}°C)\n"
                    f"💧 Humidity: {humidity}%\n"
                    f"💨 Wind: {wind_speed_kmh:.1f} km/h\n"
                    f"☔ Rain Chance: {pop:.0f}%" )
        else:
            return "Weather forecast not available for this time."

    except requests.exceptions.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return "Weather fetch failed"
    except Exception as e:
        print(f"Error processing weather data: {e}")
        return "Weather processing error"

def format_event_time(race_info, event_type):
    """Formats the event date and time into a more readable string and a datetime object.

    Args:
        race_info (dict): Dictionary containing race details.
        event_type (str): The type of event ('Race', 'Qualifying', 'Sprint', 'FirstPractice', 'SecondPractice', 'ThirdPractice').

    Returns:
        tuple: A tuple containing the formatted string and the datetime object (UTC).
               Returns (None, None) if the event time is not available.
    """
    event_key_map = {
        'Race': ('date', 'time'),
        'Qualifying': ('Qualifying', 'time'),
        'Sprint': ('Sprint', 'time'),
        'FirstPractice': ('FirstPractice', 'time'),
        'SecondPractice': ('SecondPractice', 'time'),
        'ThirdPractice': ('ThirdPractice', 'time'),
    }

    date_key = event_key_map[event_type][0]
    time_key = event_key_map[event_type][1]

    if event_type == 'Race':
        event_date_str = race_info.get('date')
        event_time_str = race_info.get('time')
    elif event_type in race_info:
         event_date_str = race_info[event_type].get('date')
         event_time_str = race_info[event_type].get('time')
    else:
        return None, None # Event type not present in race_info

    if not event_date_str or not event_time_str:
        return None, None # Date or time missing

    try:
        # Combine date and time, ensuring time has 'Z' for UTC
        if not event_time_str.endswith('Z'):
            event_time_str += 'Z'
        event_dt_str = f"{event_date_str}T{event_time_str}"
        # Parse the combined string into a timezone-aware datetime object (UTC)
        event_dt = datetime.fromisoformat(event_dt_str.replace('Z', '+00:00'))

        # Format for display (e.g., "Saturday, Jul 20, 2024 at 15:00 UTC")
        formatted_time_str = event_dt.strftime("%A, %b %d, %Y at %H:%M %Z")

        return formatted_time_str, event_dt
    except ValueError as e:
        print(f"Error parsing date/time for {event_type}: {event_date_str} {event_time_str} - {e}")
        return None, None

def create_discord_embed(race_info, event_type, event_time_str, event_dt_utc):
    """Creates a Discord embed object for the notification, including weather."""

    # Event Emojis
    event_emoji_map = {
        'Race': '🏎️',
        'Qualifying': '⏱️',
        'Sprint': '💨',
        'FirstPractice': '🔧',
        'SecondPractice': '🔧',
        'ThirdPractice': '🔧',
        'Default': '🏁' # Checkered flag as default
    }
    event_emoji = event_emoji_map.get(event_type, event_emoji_map['Default'])

    # Fetch Weather
    lat = race_info['Circuit']['Location']['lat']
    lon = race_info['Circuit']['Location']['long']
    weather_info = fetch_weather(lat, lon, event_dt_utc)

    # Construct Google Maps satellite view link
    # Use zoom level 16 for a reasonable circuit view
    maps_url = f"https://www.google.com/maps?q={lat},{lon}&t=k&z=16"

    # Construct RainViewer link using the detailed format
    rain_zoom = 9
    rain_radar_url = f"https://www.rainviewer.com/weather-radar-map-live.html?loc={lat},{lon},{rain_zoom}&oCS=1&c=3&o=83&lm=1&layer=radar&sm=1&sn=1"

    # Calculate Unix timestamp for Discord formatting
    unix_timestamp = int(event_dt_utc.timestamp())

    embed = {
        "title": f"{event_emoji} F1 {event_type} Reminder!", # Add event-specific emoji
        "description": f"The **{event_type}** session for the **[{race_info['raceName']}]({race_info['url']})** is starting soon!",
        "color": 15158332, # Keep Red color for now
        "fields": [
            {
                "name": f"{event_type} Start Time", # Remove bold
                "value": f"<t:{unix_timestamp}:R> ({event_time_str})",
                "inline": False
            },
            {
                "name": "Round", # Remove bold
                "value": race_info['round'],
                "inline": True # Keep non-inline
            },
            {
                "name": "Circuit", # Remove bold
                # Add Google Maps link to the circuit value
                "value": f"[{race_info['Circuit']['circuitName']}]({race_info['Circuit']['url']}) ([Map]({maps_url}))",
                "inline": True
            },
            {
                "name": "Location", # Remove bold
                "value": f"{race_info['Circuit']['Location']['locality']}, {race_info['Circuit']['Location']['country']}",
                "inline": False
            },
            {
                "name": ":cloud: Weather Forecast", # Remove bold
                "value": weather_info,
                "inline": False
            },
            # Add Rain Radar link field
            {
                "name": ":cloud_with_rain: Rain Radar",
                "value": f"[View Radar]({rain_radar_url})",
                "inline": False
            },
            # Add Live Timings link field
            {
                "name": "Live Timings",
                "value": "[F1 Dashboard](https://f1-dash.com/dashboard)",
                "inline": False
            }
        ],
        "footer": {
            # Use configured bot name in the footer
            "text": f"{BOT_NAME} - Season {race_info['season']}"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    return embed, event_emoji

def send_discord_notification(embed):
    """Sends the notification embed to the Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK_URL not set in .env file.")
        return

    headers = {'Content-Type': 'application/json'}
    payload = json.dumps({'embeds': [embed]})

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, headers=headers, data=payload)
        response.raise_for_status()
        print(f"Successfully sent notification for: {embed['description']}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending Discord notification: {e}")
        if response:
            print(f"Response status: {response.status_code}")
            print(f"Response text: {response.text}")

def schedule_event_notification(scheduler, race_info, event_type):
    """Schedules a notification for a specific event if it's in the future."""
    formatted_time_str, event_dt_utc = format_event_time(race_info, event_type)

    if not event_dt_utc:
        # print(f"Skipping scheduling for {event_type} in {race_info['raceName']} - time not available.")
        return

    now_utc = datetime.now(timezone.utc)
    # Use configured lead time in minutes
    notification_time = event_dt_utc - timedelta(minutes=NOTIFICATION_LEAD_MINUTES)

    # Only schedule if the notification time is in the future
    if notification_time > now_utc:
        print(f"Scheduling notification for {race_info['raceName']} {event_type} at {notification_time}")
        # Create embed here to include weather forecast at time of scheduling
        # Get both embed and emoji, though emoji isn't used here directly
        embed, _ = create_discord_embed(race_info, event_type, formatted_time_str, event_dt_utc)
        scheduler.add_job(
            send_discord_notification,
            'date',
            run_date=notification_time,
            args=[embed],
            id=f"{race_info['season']}_{race_info['round']}_{event_type}_notification", # Unique ID
            replace_existing=True # Replace if job with same ID exists
        )
    # else:
        # print(f"Skipping scheduling for {race_info['raceName']} {event_type} - notification time {notification_time} is in the past.")

def find_and_send_next_event():
    """Finds the very next upcoming F1 event and sends a notification immediately."""
    print("Finding the next upcoming F1 event to send a test notification...")
    schedule = fetch_schedule()
    if not schedule:
        print("Could not fetch schedule. Aborting test.")
        return

    next_event = None
    next_event_dt = None
    next_event_type = None
    next_race_info = None
    next_event_formatted_time = None # Store formatted time string

    now_utc = datetime.now(timezone.utc)

    # Iterate through races and then event types in their typical order
    for race in schedule:
        for event_type in EVENT_TYPES_ORDERED:
            formatted_time_str, event_dt_utc = format_event_time(race, event_type)
            if event_dt_utc and event_dt_utc > now_utc:
                # Check if this event is earlier than the current 'next_event' found
                if next_event_dt is None or event_dt_utc < next_event_dt:
                    next_event_dt = event_dt_utc
                    next_event_type = event_type
                    next_race_info = race
                    next_event_formatted_time = formatted_time_str

    if next_event_dt:
        print(f"Next event found: {next_race_info['raceName']} - {next_event_type} at {next_event_dt}")
        # Create embed here for the test message, including current weather forecast
        # Get both embed and the calculated emoji
        embed, event_emoji = create_discord_embed(next_race_info, next_event_type, next_event_formatted_time, next_event_dt)
        # Keep the test tube for test messages, but use the specific event emoji too
        embed["title"] = f":test_tube: TEST: {event_emoji} F1 {next_event_type} Reminder!"
        # Also update the description for the test notification
        # Add Race Wikipedia link here too
        embed["description"] = f"**(Test Notification)**\nThe **{next_event_type}** session for the **[{next_race_info['raceName']}]({next_race_info['url']})** is starting soon!"
        send_discord_notification(embed)
    else:
        print("No upcoming F1 events found in the current season schedule.")

def schedule_all_notifications():
    """Fetches the schedule and schedules notifications for all future events."""
    print("Fetching F1 schedule and scheduling notifications...")
    schedule = fetch_schedule()
    if not schedule:
        print("Could not fetch schedule. Aborting scheduling.")
        return

    scheduler = BlockingScheduler(timezone="UTC")

    event_types = ['Race', 'Qualifying', 'Sprint', 'FirstPractice', 'SecondPractice', 'ThirdPractice']

    for race in schedule:
        for event_type in event_types:
            schedule_event_notification(scheduler, race, event_type)

    if not scheduler.get_jobs():
        print("No future events found to schedule.")
    else:
        print("Starting scheduler...")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            print("Scheduler stopped.")
            scheduler.shutdown()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F1 Event Reminder Bot")
    parser.add_argument(
        '--test-next-event',
        action='store_true',
        help='Send a test notification for the next upcoming event immediately.'
    )
    args = parser.parse_args()

    if args.test_next_event:
        find_and_send_next_event()
    else:
        schedule_all_notifications() 