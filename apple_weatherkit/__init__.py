from enum import StrEnum

class DataSetType(StrEnum):
    CURRENT_WEATHER = "currentWeather"
    DAILY_FORECAST = "forecastDaily"
    HOURLY_FORECAST = "forecastHourly"
    NEXT_HOUR_FORECAST = "forecastNextHour"
    WEATHER_ALERTS = "weatherAlerts"
