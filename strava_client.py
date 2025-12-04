import os
import requests
from datetime import datetime, timedelta
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")

# In-memory token storage (Same as before, but encapsulated)
user_tokens = {
    "user123": {
        "access_token": os.getenv("STRAVA_ACCESS_TOKEN"),
        "refresh_token": os.getenv("STRAVA_REFRESH_TOKEN"),
        "expires_at": int(datetime.now().timestamp()) - 3600 
    }
}

def get_access_token(user_id: str):
    if user_id not in user_tokens:
        raise HTTPException(status_code=401, detail="User not authenticated")

    token_info = user_tokens[user_id]
    
    if datetime.now().timestamp() > token_info["expires_at"] - 60: 
        print("Attempting to refresh Strava token...")
        refresh_url = "https://www.strava.com/oauth/token"
        payload = {
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "refresh_token": token_info["refresh_token"],
            "grant_type": "refresh_token"
        }
        try:
            response = requests.post(refresh_url, data=payload)
            response.raise_for_status()
            new_tokens = response.json()
            token_info["access_token"] = new_tokens["access_token"]
            token_info["refresh_token"] = new_tokens.get("refresh_token", token_info["refresh_token"]) 
            token_info["expires_at"] = new_tokens["expires_at"]
            print("Strava token refreshed successfully.")
        except requests.exceptions.RequestException as e:
            print(f"Token refresh failed: {e}")
            raise HTTPException(status_code=500, detail=f"Token refresh failed: {e}")
    
    return token_info["access_token"]

def fetch_recent_activities(user_id: str, days: int = 7):
    try:
        access_token = get_access_token(user_id)
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        url = f"https://www.strava.com/api/v3/athlete/activities?after={since}"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Strava fetch failed: {e}")
        raise HTTPException(status_code=500, detail=f"Strava fetch failed: {e}")

def fetch_activity_streams(user_id: str, activity_id: int):
    # This uses the logic we had in processor, but placed here for clean data access
    stream_types = ['time', 'latlng', 'distance', 'altitude', 'heartrate', 'cadence', 'watts', 'velocity_smooth']
    try:
        access_token = get_access_token(user_id)
        keys_param = ",".join(stream_types)
        url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams?keys={keys_param}&key_by_type=true&resolution=low"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        streams_data = response.json()
        
        formatted_streams = {}
        for stream_dict in streams_data:
            if 'type' in stream_dict:
                formatted_streams[stream_dict['type']] = stream_dict['data']
        return formatted_streams
    except Exception as e:
        print(f"Error fetching streams: {e}")
        return None
