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
# Revert back to the jolpi.ca mirror
F1_API_URL = "https://api.jolpi.ca/ergast/f1/current.json" # Use jolpi.ca mirror
# F1_API_URL = "https://ergast.com/api/f1/current.json" # Official Ergast API endpoint (being deprecated)
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

# --- Mappings ---
ERG_TO_OPENF1_CIRCUIT_MAP = {
    "bahrain": 48,
    "jeddah": 70,
    "albert_park": 58, # Melbourne
    "suzuka": 22,
    "shanghai": 17,
    "miami": 73,
    "imola": 21,
    "monaco": 6,
    "villeneuve": 7, # Canada
    "catalunya": 4, # Spain
    "red_bull_ring": 9, # Austria
    "silverstone": 3, # Great Britain
    "hungaroring": 10, # Hungary
    "spa": 5, # Belgium
    "zandvoort": 11, # Netherlands
    "monza": 13, # Italy
    "baku": 67, # Azerbaijan
    "marina_bay": 15, # Singapore
    "americas": 63, # USA (COTA)
    "rodriguez": 16, # Mexico
    "interlagos": 18, # Brazil
    "vegas": 77, # Las Vegas
    "losail": 75, # Qatar
    "yas_marina": 24 # Abu Dhabi
    # Add more mappings as needed if new circuits appear
}

# Define event types in order of typical occurrence within a race weekend
EVENT_TYPES_ORDERED = ['FirstPractice', 'SecondPractice', 'ThirdPractice', 'Sprint', 'Qualifying', 'Race']
EVENT_TYPES_REVERSED = list(reversed(EVENT_TYPES_ORDERED))


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

def fetch_starting_grid(season, round_num):
    """Fetches the starting grid (qualifying results) for a specific race round."""
    # Use the round-specific endpoint - Use jolpi.ca mirror
    grid_url = f"https://api.jolpi.ca/ergast/f1/{season}/{round_num}/qualifying.json"
    # grid_url = f"https://ergast.com/api/f1/{season}/{round_num}/qualifying.json" # Official Ergast API endpoint (being deprecated)
    print(f"Fetching starting grid from: {grid_url}") # Updated log message
    try:
        response = requests.get(grid_url)
        response.raise_for_status()
        data = response.json()

        races_data = data.get('MRData', {}).get('RaceTable', {}).get('Races', [])
        if not races_data:
            # This might happen if the round number is invalid or qualifying data doesn't exist yet
            print(f"No race data found in qualifying response for {season} round {round_num}.")
            return None

        # Since we requested a specific round, we expect only one race object
        target_race = races_data[0]

        qualifying_results = target_race.get('QualifyingResults', [])
        if not qualifying_results:
            print(f"No qualifying results found for round {round_num}.")
            return None

        # Sort by position just in case the API doesn't guarantee it (it usually does)
        qualifying_results.sort(key=lambda x: int(x.get('position', 99)))
        print(f"Successfully found {len(qualifying_results)} qualifying results for round {round_num}.")
        return qualifying_results

    except requests.exceptions.RequestException as e:
        # Check for 404 or other errors that might indicate missing data for the specific round
        if response is not None and response.status_code == 404:
             print(f"Qualifying data not found (404) for {season} round {round_num}.")
        else:
             print(f"Error fetching starting grid: {e}")
        return None
    except json.JSONDecodeError:
        print("Error decoding JSON response from qualifying API.")
        return None
    except IndexError:
         print(f"Error accessing race data for round {round_num}. Response structure might be unexpected.")
         return None
    except Exception as e:
        print(f"An unexpected error occurred fetching grid: {e}")
        return None

def fetch_starting_grid_openf1(season, circuit_id):
    """Fetches the starting grid (qualifying results) for a specific race using OpenF1 API."""
    print(f"Attempting OpenF1 fallback for {season} at {circuit_id}")

    circuit_key = ERG_TO_OPENF1_CIRCUIT_MAP.get(circuit_id)
    if not circuit_key:
        print(f"  Error: OpenF1 circuit_key not found for Ergast circuitId '{circuit_id}'. Cannot fetch grid.")
        return None

    openf1_session_url = f"https://api.openf1.org/v1/sessions?year={season}&circuit_key={circuit_key}&session_name=Qualifying"
    session_key = None

    try:
        # 1. Find the session_key for Qualifying
        print(f"  Fetching OpenF1 session key from: {openf1_session_url}")
        response = requests.get(openf1_session_url)
        response.raise_for_status()
        sessions_data = response.json()
        if not sessions_data:
            print(f"  Error: No OpenF1 Qualifying session found for {season}, circuit_key {circuit_key}.")
            return None
        # Assume the first (and likely only) result is the correct one
        session_key = sessions_data[0].get('session_key')
        if not session_key:
             print(f"  Error: Could not extract session_key from OpenF1 response.")
             return None
        print(f"  Found OpenF1 session_key: {session_key}")

        # 2. Fetch the results for that session_key
        openf1_results_url = f"https://api.openf1.org/v1/results?session_key={session_key}"
        print(f"  Fetching OpenF1 results from: {openf1_results_url}")
        response = requests.get(openf1_results_url)
        response.raise_for_status()
        results_data = response.json()
        if not results_data:
            print(f"  Error: No OpenF1 results found for session_key {session_key}.")
            return None

        # 3. Parse and reformat results
        formatted_grid = []
        for result in results_data:
            # Ensure position exists and is a valid number for sorting
            position = result.get('position')
            if position is None:
                continue # Skip drivers without a position (e.g., DNS)
            try:
                position = int(position)
            except (ValueError, TypeError):
                continue # Skip if position is not a valid integer

            family_name = result.get('family_name')
            if not family_name:
                # Fallback to full name if family name missing
                family_name = result.get('full_name', 'N/A')

            formatted_grid.append({
                'position': position,
                'Driver': {'familyName': family_name}
            })

        if not formatted_grid:
            print("  Error: Could not format any valid grid positions from OpenF1 results.")
            return None

        # 4. Sort by position
        formatted_grid.sort(key=lambda x: x['position'])
        print(f"  Successfully fetched and formatted {len(formatted_grid)} grid positions from OpenF1.")
        return formatted_grid

    except requests.exceptions.RequestException as e:
        print(f"  Error fetching OpenF1 data: {e}")
        return None
    except json.JSONDecodeError:
        print(f"  Error decoding JSON response from OpenF1 API.")
        return None
    except IndexError:
         print(f"  Error accessing OpenF1 data. Response structure might be unexpected.")
         return None
    except Exception as e:
        print(f"  An unexpected error occurred fetching OpenF1 grid: {e}")
        return None

def fetch_weather(lat, lon, event_dt_utc):
    """Fetches weather forecast for the given coordinates around the event time.
       Returns a tuple: (formatted_weather_string_without_rain_chance, pop_percentage)
    """
    if not WEATHER_API_KEY:
        print("Weather API key not configured. Skipping weather fetch.")
        return "Weather N/A (No API Key)", 0 # Return 0 for pop

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


            # Format the string nicely, EXCLUDING rain chance for now
            weather_string = (
                f"{weather_icon} {weather_desc}\n" # Weather description
                f"🌡️ Temp: {temp:.1f}°C (Feels like: {feels_like:.1f}°C)\n"
                f"💧 Humidity: {humidity}%\n"
                f"💨 Wind: {wind_speed_kmh:.1f} km/h"
            )
            return weather_string, pop # Return string and pop value separately
        else:
            return "Weather forecast not available for this time.", 0

    except requests.exceptions.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return "Weather fetch failed", 0
    except Exception as e:
        print(f"Error processing weather data: {e}")
        return "Weather processing error", 0

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
    weather_string, pop = fetch_weather(lat, lon, event_dt_utc)

    # Construct Google Maps satellite view link
    # Use zoom level 16 for a reasonable circuit view
    maps_url = f"https://www.google.com/maps?q={lat},{lon}&t=k&z=16"

    # Construct RainViewer link using the detailed format
    rain_zoom = 9
    rain_radar_url = f"https://www.rainviewer.com/weather-radar-map-live.html?loc={lat},{lon},{rain_zoom}&oCS=1&c=3&o=83&lm=1&layer=radar&sm=1&sn=1"

    # Append rain chance and radar link to the weather string
    weather_field_value = f"{weather_string}\n☔ Rain Chance: {pop:.0f}% ([Radar]({rain_radar_url}))"

    # Calculate Unix timestamp for Discord formatting
    unix_timestamp = int(event_dt_utc.timestamp())

    # --- Fetch and Format Starting Grid (only for Race events) ---
    grid_field = None
    if event_type == 'Race':
        # Try Ergast first
        grid_data = fetch_starting_grid(race_info['season'], race_info['round'])

        # If Ergast fails, try OpenF1
        if grid_data is None:
            print("Ergast grid data not found. Falling back to OpenF1...")
            grid_data = fetch_starting_grid_openf1(race_info['season'], race_info['Circuit']['circuitId'])

        # Only proceed if grid_data is actually found (from either source)
        if grid_data:
            grid_lines = []
            max_len_left = 0
            pairs = []
            # Prepare pairs and find max lengths for consistent formatting
            for i in range(0, len(grid_data), 2):
                pos1_str = f"P{grid_data[i]['position']}"
                driver1_name = grid_data[i]['Driver'].get('familyName', 'N/A')
                left_col = f"{pos1_str:<3} {driver1_name}" # Pad position to 3 chars (e.g., P1 , P10)
                max_len_left = max(max_len_left, len(left_col))

                right_col = ""
                if i + 1 < len(grid_data):
                    pos2_str = f"P{grid_data[i+1]['position']}"
                    driver2_name = grid_data[i+1]['Driver'].get('familyName', 'N/A')
                    right_col = f"{pos2_str:<3} {driver2_name}"

                pairs.append((left_col, right_col))

            # Build the final lines, padding the left column
            for left, right in pairs:
                grid_lines.append(f"{left:<{max_len_left}} | {right}")

            # Only create the field if we successfully formatted grid lines
            if grid_lines:
                grid_field_value = "```\n" + "\n".join(grid_lines) + "\n```"
                grid_field = {
                    "name": "🏁 Starting Grid",
                    "value": grid_field_value,
                    "inline": False
                }
            # If formatting failed or grid_lines is empty, grid_field remains None
        # If grid_data was None initially, grid_field remains None
    # --- End Grid Fetch and Format ---

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
                "value": weather_field_value, # Use the combined string
                "inline": False
            },
            # Add Live Timings link field
            {
                "name": "Live Timings",
                "value": "[F1 Dashboard](https://f1-dash.com/dashboard)",
                "inline": True
            },
            # Add Radio Transcripts link field
            {
                "name": "📻 Radio Transcripts",
                "value": "[Box Box Radio](https://www.boxbox-radio.com/radios)",
                "inline": True
            }
        ],
        "footer": {
            # Use configured bot name in the footer
            "text": f"{BOT_NAME} - Season {race_info['season']}"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Add the grid field if it was created (i.e., if event_type is Race)
    if grid_field:
        embed['fields'].append(grid_field)

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

def find_and_send_previous_event():
    """Finds the most recently completed F1 event and sends a notification immediately."""
    print("Finding the most recently completed F1 event to send a test notification...")
    schedule = fetch_schedule()
    if not schedule:
        print("Could not fetch schedule. Aborting test.")
        return

    # Determine the latest season year in the fetched data
    latest_season = None
    try:
        seasons = {int(race.get('season')) for race in schedule if race.get('season')}
        if seasons:
            latest_season = str(max(seasons))
            print(f"Latest season found in schedule data: {latest_season}")
        else:
            print("Could not determine latest season from schedule data.")
            return
    except (ValueError, TypeError):
         print("Error determining latest season from schedule data.")
         return

    # Filter schedule to only include races from the latest season
    latest_season_schedule = [race for race in schedule if race.get('season') == latest_season]
    if not latest_season_schedule:
        print(f"No races found for the latest season ({latest_season}) in the schedule data.")
        return

    previous_event_dt = None
    previous_event_type = None
    previous_race_info = None
    previous_event_formatted_time = None

    now_utc = datetime.now(timezone.utc)

    # Iterate through races of the LATEST season only
    # Iterate through event types in REVERSE order to find the latest past event
    for race in latest_season_schedule: # Iterate races chronologically within the latest season
        for event_type in EVENT_TYPES_REVERSED: # Iterate events within race weekend backwards
            formatted_time_str, event_dt_utc = format_event_time(race, event_type)
            # Check if the event time is valid AND in the past
            if event_dt_utc and event_dt_utc < now_utc:
                # Is this event later than the current 'previous_event' found?
                if previous_event_dt is None or event_dt_utc > previous_event_dt:
                    previous_event_dt = event_dt_utc
                    previous_event_type = event_type
                    previous_race_info = race
                    previous_event_formatted_time = formatted_time_str

    if previous_event_dt:
        print(f"Most recent past event found: {previous_race_info['raceName']} - {previous_event_type} at {previous_event_dt}")
        # Create embed for the test message
        embed, event_emoji = create_discord_embed(previous_race_info, previous_event_type, previous_event_formatted_time, previous_event_dt)
        embed["title"] = f":rewind: TEST (Previous): {event_emoji} F1 {previous_event_type} Reminder!"
        # Update description for test message
        embed["description"] = f"**(Test Notification - Previous Event)**\nThe **{previous_event_type}** session for the **[{previous_race_info['raceName']}]({previous_race_info['url']})** occurred {previous_event_formatted_time}."
        # Remove timestamp for past events?
        # embed.pop("timestamp", None)
        send_discord_notification(embed)
    else:
        print(f"No past F1 events found in the latest season ({latest_season}) schedule.")

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
    # Group test flags so only one can be used
    test_group = parser.add_mutually_exclusive_group()
    test_group.add_argument(
        '--test-next-event',
        action='store_true',
        help='Send a test notification for the next upcoming event immediately.'
    )
    test_group.add_argument(
        '--test-previous-event',
        action='store_true',
        help='Send a test notification for the most recently completed event immediately.'
    )
    args = parser.parse_args()

    if args.test_next_event:
        find_and_send_next_event()
    elif args.test_previous_event:
        find_and_send_previous_event()
    else:
        schedule_all_notifications() 