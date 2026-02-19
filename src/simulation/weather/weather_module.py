 
# Install (run these in terminal, not in Python): 
# pip install openmeteo-requests 
# pip install requests-cache retry-requests numpy pandas  
# "https://open-meteo.com/
# "https://open-meteo.com/en/docs?hourly=temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,surface_pressure,cloud_cover,wind_gusts_10m,visibility,rain,snowfall,showers&daily=uv_index_max,weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,snowfall_sum,showers_sum,rain_sum,cloud_cover_mean,surface_pressure_max,surface_pressure_min,wind_speed_10m_mean,wind_gusts_10m_mean,winddirection_10m_dominant,wind_direction_10m_dominant,relative_humidity_2m_max,relative_humidity_2m_min,shortwave_radiation_sum,dew_point_2m_mean,dew_point_2m_max,dew_point_2m_min&temperature_unit=fahrenheit&timezone=America%2FNew_York&latitude=30.1555&longitude=-95.5938&current=pressure_msl,surface_pressure
# "https://www.khanacademy.org/computing/tesda-computational-thinking/xed777e2cccd04061:introduction/xed777e2cccd04061:arithmetic-expressions/a/python-style-guide
 
import openmeteo_requests 
import pandas as pd 
import requests_cache 
from retry_requests import retry 
 
# --------------------------------------------- 
#   Setup API Client (with caching + retries) 
# --------------------------------------------- 
cache_session = requests_cache.CachedSession('.cache', expire_after=3600) 
retry_session = retry(cache_session, retries=5, backoff_factor=0.2) 
openmeteo = openmeteo_requests.Client(session=retry_session) 
 
# --------------------------------------------- 
#   API Request Parameters 
# --------------------------------------------- 
url = "https://api.open-meteo.com/v1/forecast" 
 
params = { 
   "latitude": 30.1555, 
   "longitude": -95.5938, 
   "daily": [ 
       "uv_index_max", "weather_code", "temperature_2m_max", "temperature_2m_min", 
       "precipitation_sum", "snowfall_sum", "showers_sum", "rain_sum", 
       "cloud_cover_mean", "surface_pressure_max", "surface_pressure_min", 
       "wind_speed_10m_mean", "wind_gusts_10m_mean", 
       "winddirection_10m_dominant", "wind_direction_10m_dominant", 
       "relative_humidity_2m_max", "relative_humidity_2m_min", 
       "shortwave_radiation_sum", "dew_point_2m_mean", "dew_point_2m_max", "dew_point_2m_min",
   ], 
   "hourly": [ 
       "temperature_2m", "relative_humidity_2m", "dew_point_2m", 
       "precipitation", "surface_pressure", "cloud_cover", 
       "wind_gusts_10m", "visibility", "rain", "snowfall", "showers" 
   ], 
   "timezone": "America/New_York", 
   "temperature_unit": "fahrenheit", 
} 
 
# --------------------------------------------- 
#   Make API Request 
# --------------------------------------------- 
responses = openmeteo.weather_api(url, params=params) 
response = responses[0] 
 
print(f"Coordinates: {response.Latitude()}°N, {response.Longitude()}°E") 
print(f"Elevation: {response.Elevation()} m") 
print(f"Timezone: {response.Timezone()} ({response.TimezoneAbbreviation()})") 
print(f"UTC Offset: {response.UtcOffsetSeconds()} seconds") 
 
# --------------------------------------------- 
#   Process Hourly Data 
# --------------------------------------------- 
hourly = response.Hourly() 
 
hourly_data = { 
   "date": pd.date_range( 
       start=pd.to_datetime(hourly.Time() + response.UtcOffsetSeconds(), unit="s", utc=True), 
       end=pd.to_datetime(hourly.TimeEnd() + response.UtcOffsetSeconds(), unit="s", utc=True), 
       freq=pd.Timedelta(seconds=hourly.Interval()), 
       inclusive="left" 
   ) 
} 
 
hourly_variables = [ 
   "temperature_2m", "relative_humidity_2m", "dew_point_2m", 
   "precipitation", "surface_pressure", "cloud_cover", 
   "wind_gusts_10m", "visibility", "rain", "snowfall", "showers" 
] 
 
for i, var in enumerate(hourly_variables): 
   hourly_data[var] = hourly.Variables(i).ValuesAsNumpy() 
 
hourly_df = pd.DataFrame(hourly_data) 
print("\nHourly Data:") 
print(hourly_df) 
 
# --------------------------------------------- 
#   Process Daily Data 
# --------------------------------------------- 
daily = response.Daily() 
 
daily_data = { 
   "date": pd.date_range( 
       start=pd.to_datetime(daily.Time() + response.UtcOffsetSeconds(), unit="s", utc=True), 
       end=pd.to_datetime(daily.TimeEnd() + response.UtcOffsetSeconds(), unit="s", utc=True), 
       freq=pd.Timedelta(seconds=daily.Interval()), 
       inclusive="left" 
   ) 
} 
 
daily_variables = [ 
   "uv_index_max", "weather_code", "temperature_2m_max", "temperature_2m_min", 
   "precipitation_sum", "snowfall_sum", "showers_sum", "rain_sum", 
   "cloud_cover_mean", "surface_pressure_max", "surface_pressure_min", 
   "wind_speed_10m_mean", "wind_gusts_10m_mean", 
   "winddirection_10m_dominant", "wind_direction_10m_dominant", 
   "relative_humidity_2m_max", "relative_humidity_2m_min", 
   "shortwave_radiation_sum, daily_dew_point_2m_mean, daily_dew_point_2m_max, daily_dew_point_2m_min
] 
 
for i, var in enumerate(daily_variables): 
   daily_data[var] = daily.Variables(i).ValuesAsNumpy() 
 
daily_df = pd.DataFrame(daily_data) 
print("\nDaily Data:") 
print(daily_df) 

 

for i, var in enumerate(daily_variables): daily_data[var] = daily.Variables(i).ValuesAsNumpy() 

daily_df = pd.DataFrame(daily_data) print("\nDaily Data:") print(daily_df) 

 