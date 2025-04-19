# F1 Discord Reminder Bot

A Python bot that sends reminders for upcoming Formula 1 race weekend sessions (Practice, Qualifying, Sprint, Race) to a Discord webhook.

## Features

*   Fetches the current F1 season schedule from the Ergast API.
*   Sends notifications to a specified Discord webhook URL.
*   Configurable lead time (in minutes) before each session to send the reminder.
*   Includes upcoming session details: Round, Circuit (with Wikipedia link), Location, Start Time (relative and absolute UTC).
*   Provides additional useful links:
    *   Google Maps satellite view of the circuit.
    *   RainViewer radar link for the circuit area.
    *   Live timings link (f1-dash.com).
*   Fetches and displays approximate weather forecast for the session time using OpenWeatherMap.
*   Includes a test mode (`--test-next-event`) to send a notification for the very next upcoming event immediately.
*   Configurable bot name displayed in the footer.
*   Can be run using Docker.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd discord-f1-reminder
    ```
2.  **Create the environment file:**
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   Edit the `.env` file and fill in your details (see Configuration below).
3.  **Install dependencies:**
    *   It's recommended to use a virtual environment:
        ```bash
        python -m venv .venv
        # On Windows PowerShell
        .\.venv\Scripts\Activate.ps1
        # On Linux/macOS bash/zsh
        # source .venv/bin/activate
        ```
    *   Install the required packages:
        ```bash
        pip install -r requirements.txt
        ```

## Configuration

Edit the `.env` file with your specific details:

*   `DISCORD_WEBHOOK_URL`: **Required.** Your Discord channel's webhook URL.
*   `WEATHER_API_KEY`: **Required.** Your API key from [OpenWeatherMap](https://openweathermap.org/) (free tier is sufficient). Needed for weather forecasts.
*   `NOTIFICATION_LEAD_MINUTES`: Optional. The number of minutes before a session starts to send the notification. Defaults to `180` (3 hours) if not set or invalid.
*   `BOT_NAME`: Optional. The name displayed in the footer of the reminder embed. Defaults to `F1 Reminder Bot`.

## Running the Bot

### Directly

Ensure your virtual environment is active (if using one).

*   **Normal Mode (Schedules future events):**
    ```bash
    python main.py
    ```
    The bot will fetch the schedule, schedule all future notifications, and run until interrupted (`Ctrl+C`).

*   **Test Mode (Sends next upcoming event immediately):**
    ```bash
    python main.py --test-next-event
    ```

### Using Docker

1.  **Build the Docker image:**
    ```bash
    docker build -t f1-reminder-bot .
    ```
2.  **Run the Docker container:**
    *   You need to pass your `.env` file to the container so it can access your secrets and configuration.
    ```bash
    # Replace $(pwd) with %cd% on Windows Command Prompt if needed
    docker run --rm --env-file .env f1-reminder-bot
    ```
    *   To run the test command inside Docker:
    ```bash
    docker run --rm --env-file .env f1-reminder-bot --test-next-event
    ```

## Disclaimer

This project is unofficial and is not associated in any way with the Formula 1 companies. F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD CHAMPIONSHIP, GRAND PRIX and related marks are trademarks of Formula One Licensing B.V. 