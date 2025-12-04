from strava_client import fetch_recent_activities, fetch_activity_streams
from processor import process_activities, analyze_streams, calculate_progression
from user_profile import get_user_profile, update_user_profile

# --- Tool Functions for Gemini ---

def get_recent_activities_summary(user_id: str):
    """
    Fetches the user's recent activities (last 14 days) and returns a summary 
    including Heart Rate Zones, Suffer Scores, and Power-to-Weight (if weight is known).
    """
    raw_data = fetch_recent_activities(user_id, days=14)
    if not raw_data:
        return "No recent activities found."
    
    profile = get_user_profile(user_id)
    weight = profile.get("weight_kg")
    
    processed = process_activities(raw_data, user_weight_kg=weight)
    
    # Format for LLM consumption
    summary = f"Found {len(processed)} activities in the last 14 days:\n"
    for act in processed:
        summary += f"- ID: {act['id']} | {act['name']} ({act['date']}): {act['distance_km']}km, {act['elevation_m']}m elev, {act['ride_type']}. "
        if act.get('watts_per_kg') != "N/A (Weight needed)":
            summary += f"Power: {act['watts_per_kg']} W/kg. "
        summary += f"Intensity: {act['suffer_score_interpretation']}.\n"
        
    return summary

def analyze_specific_ride_depth(user_id: str, activity_id: int):
    """
    Performs a deep-dive analysis on a specific ride using its data streams 
    (Heart Rate, Speed, Cadence, Watts). activity_id can be found in the summary.
    """
    # First get the name for context
    # (In a real app, we might cache this, but fetching list again is safe/fast enough for now or we just use ID)
    activity_name = f"Activity {activity_id}" 
    
    streams = fetch_activity_streams(user_id, activity_id)
    if not streams:
        return "Could not fetch detailed data streams for this activity."
        
    analysis = analyze_streams(streams, activity_name)
    return analysis

def check_progression(user_id: str):
    """
    Compares the current week's volume and intensity against the last 4 weeks 
    to determine if the user is progressing or fatigued.
    """
    # Fetch 30 days of data
    raw_data = fetch_recent_activities(user_id, days=30)
    if not raw_data:
        return "Not enough data to check progression."
        
    # Split into current week vs past
    # (Simple logic: assuming ordered by date desc)
    # Actually raw Strava data is usually date desc.
    # We'll do a robust date split.
    from datetime import datetime, timedelta
    
    now = datetime.now()
    seven_days_ago = now - timedelta(days=7)
    
    current_week = []
    past_weeks = []
    
    for act in raw_data:
        act_date = datetime.strptime(act['start_date_local'].split("T")[0], "%Y-%m-%d")
        processed_act = process_activities([act])[0] # Process individually to get metrics
        
        if act_date > seven_days_ago:
            current_week.append(processed_act)
        else:
            past_weeks.append(processed_act)
            
    return calculate_progression(current_week, past_weeks)

def update_user_physical_stats(user_id: str, weight_kg: float = None, ftp: int = None):
    """
    Updates the user's physical profile (Weight in kg, FTP in watts).
    Call this if the user provides this information.
    """
    updated = update_user_profile(user_id, weight_kg, ftp)
    return f"Profile updated. Weight: {updated.get('weight_kg', '?')}kg, FTP: {updated.get('ftp', '?')}W."

# Map tools for easy access by name in app.py
tool_registry = {
    "get_recent_activities_summary": get_recent_activities_summary,
    "analyze_specific_ride_depth": analyze_specific_ride_depth,
    "check_progression": check_progression,
    "update_user_physical_stats": update_user_physical_stats
}
