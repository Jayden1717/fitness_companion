# processor.py
# This file contains functions to process raw Strava data into enriched insights,
# including handling granular activity streams.

import json
from datetime import datetime, timedelta
import requests
from fastapi import HTTPException # Used for structured error handling

# --- Existing summary functions (get_primary_hr_zone, interpret_suffer_score, classify_ride_type) ---
def get_primary_hr_zone(average_hr, max_hr):
    if not average_hr or not max_hr or max_hr == 0: return "N/A"
    zones = {
        "Zone 1 (Recovery)": max_hr * 0.6, "Zone 2 (Endurance)": max_hr * 0.7,
        "Zone 3 (Tempo)": max_hr * 0.8, "Zone 4 (Threshold)": max_hr * 0.9,
    }
    if average_hr < zones["Zone 1 (Recovery)"]: return "Zone 1 (Recovery)"
    elif average_hr < zones["Zone 2 (Endurance)"]: return "Zone 2 (Endurance)"
    elif average_hr < zones["Zone 3 (Tempo)"]: return "Zone 3 (Tempo)"
    elif average_hr < zones["Zone 4 (Threshold)"]: return "Zone 4 (Threshold)"
    else: return "Zone 5 (Anaerobic)"

def interpret_suffer_score(score):
    if score is None: return "N/A"
    if score < 25: return f"{score} (Light Effort)"
    elif score < 75: return f"{score} (Moderate Effort)"
    elif score < 125: return f"{score} (Tough Workout)"
    else: return f"{score} (All-Out Effort)"

def classify_ride_type(distance_m, elevation_m):
    if distance_m == 0: return "Stationary"
    climb_ratio = elevation_m / (distance_m / 1000) # Meters of climbing per km
    if climb_ratio > 20: return "Mountainous Climb"
    elif climb_ratio > 10: return "Hilly Ride"
    elif distance_m > 80000: return "Long Endurance Ride" # Over 80km
    else: return "Rolling/Flat Ride"

# --- NEW: Advanced Metrics Helpers ---

def calculate_power_to_weight(watts, weight_kg):
    if not watts or not weight_kg or weight_kg == 0:
        return None
    return round(watts / weight_kg, 2)

def estimate_vo2max(max_hr, resting_hr=60):
    # Simple Uth-Sørensen-Overgaard-Pedersen estimation
    # VO2max ≈ 15.3 x (MHR / RHR)
    # This is a VERY rough estimate. 
    if not max_hr: return None
    return round(15.3 * (max_hr / resting_hr), 1)

def calculate_progression(current_week_activities, past_month_activities):
    """
    Compares current week's total distance/elevation vs the average of the past 4 weeks.
    Returns a text summary.
    """
    if not past_month_activities:
        return "Not enough historical data to calculate progression."
    
    # Simple logic: Sum distance for current week (passed in as list)
    current_dist = sum(act.get("distance_km", 0) for act in current_week_activities)
    current_elev = sum(act.get("elevation_m", 0) for act in current_week_activities)
    
    # Past month average (assuming past_month_activities is roughly 4 weeks)
    past_dist = sum(act.get("distance_km", 0) for act in past_month_activities)
    past_elev = sum(act.get("elevation_m", 0) for act in past_month_activities)
    
    # Normalize past to "per week" if it's a full month (approx 4 weeks)
    avg_past_dist_weekly = past_dist / 4
    avg_past_elev_weekly = past_elev / 4
    
    if avg_past_dist_weekly == 0: avg_past_dist_weekly = 1 # Avoid div by zero
    
    dist_diff_percent = ((current_dist - avg_past_dist_weekly) / avg_past_dist_weekly) * 100
    
    trend = "improving" if dist_diff_percent > 0 else "decreasing"
    
    return f"Your weekly volume is {abs(int(dist_diff_percent))}% {trend} compared to your 4-week average."


# --- Function to process summary activities (as before, with athlete_count added) ---
def process_activities(activities_json: list, user_weight_kg: float = None) -> list:
    processed_activities = []
    for act in activities_json:
        insights = {
            "id": act.get("id"), # Crucial for fetching streams later
            "name": act.get("name"),
            "date": act.get("start_date_local", "").split("T")[0],
            "distance_km": round(act.get("distance", 0) / 1000, 1),
            "elevation_m": int(act.get("total_elevation_gain", 0)),
            "moving_time_min": round(act.get("moving_time", 0) / 60, 1),
            "pr_count": act.get("pr_count", 0),
            "athlete_count": act.get("athlete_count", 1),
            "average_watts": act.get("average_watts"),
            "weighted_average_watts": act.get("weighted_average_watts"),
        }
        
        # Calculate W/kg if weight is available and watts are present
        avg_watts = act.get("average_watts")
        if user_weight_kg and avg_watts:
            insights["watts_per_kg"] = calculate_power_to_weight(avg_watts, user_weight_kg)
        else:
            insights["watts_per_kg"] = "N/A (Weight needed)"

        insights["ride_type"] = classify_ride_type(act.get("distance", 0), act.get("total_elevation_gain", 0))
        insights["suffer_score_interpretation"] = interpret_suffer_score(act.get("suffer_score"))
        insights["primary_hr_zone"] = get_primary_hr_zone(act.get("average_heartrate"), act.get("max_heartrate"))
        
        processed_activities.append(insights)
    return processed_activities

# --- NEW: Function to get granular activity streams ---
def get_activity_streams(get_access_token_func, user_id: str, activity_id: int, stream_types: list = None, resolution: str = 'low'):
    """
    Fetches detailed activity streams for a specific activity ID.
    
    Args:
        get_access_token_func: A callable function to get the user's Strava access token.
        user_id: The user's ID.
        activity_id: The ID of the Strava activity.
        stream_types: A list of strings for the desired stream types.
        resolution: 'low', 'medium', or 'high'.
    
    Returns:
        A dictionary where keys are stream types and values are their data.
    """
    if stream_types is None:
        stream_types = ['time', 'latlng', 'distance', 'altitude', 'heartrate', 'cadence', 'watts', 'velocity_smooth']

    try:
        access_token = get_access_token_func(user_id) # Use the passed function
        keys_param = ",".join(stream_types)

        url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams?keys={keys_param}&key_by_type=true&resolution={resolution}"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        streams_data = response.json()
        
        formatted_streams = {}
        for stream_dict in streams_data:
            if 'type' in stream_dict:
                formatted_streams[stream_dict['type']] = stream_dict['data'] # Just store the data list
        
        return formatted_streams
        
    except requests.exceptions.RequestException as e:
        error_detail = "Unknown Strava API error fetching streams."
        if e.response:
            try:
                error_json = e.response.json()
                error_detail = error_json.get("message", error_detail) + ": " + json.dumps(error_json.get("errors", []))
            except json.JSONDecodeError:
                error_detail = e.response.text
        print(f"ERROR: Strava stream fetch failed for activity {activity_id}: {e}")
        raise HTTPException(status_code=e.response.status_code if e.response else 500, detail=f"Failed to fetch activity streams: {error_detail}")
    except Exception as e:
        print(f"ERROR: An unexpected error occurred in get_activity_streams: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error during stream fetch: {e}")


# --- NEW: Helper for detailed stream analysis (example of a "sub-agent" task) ---
def analyze_streams(stream_data: dict, activity_name: str) -> str:
    """
    Performs specific analysis on stream data and returns a human-readable summary.
    This is where your 'analysis agent' logic would live.
    """
    analysis_results = []

    if not stream_data:
        return f"No detailed stream data available for {activity_name} to perform analysis."

    # Example: Analyze Heart Rate variability and peaks
    if 'heartrate' in stream_data and stream_data['heartrate']:
        hr_data = stream_data['heartrate']
        max_hr = max(hr_data)
        min_hr = min(hr_data)
        avg_hr = sum(hr_data) / len(hr_data)
        
        analysis_results.append(f"Heart Rate Analysis for '{activity_name}':")
        analysis_results.append(f"  - Max HR: {max_hr} bpm")
        analysis_results.append(f"  - Min HR: {min_hr} bpm")
        analysis_results.append(f"  - Avg HR: {avg_hr:.1f} bpm")
        
        # Simple detection of sustained high effort
        high_effort_threshold = max_hr * 0.85 # e.g., 85% of max
        time_at_high_effort = sum(1 for hr in hr_data if hr >= high_effort_threshold) * 10 # Assuming 'low' resolution (10s intervals)
        if time_at_high_effort > 0:
            analysis_results.append(f"  - Spent approximately {round(time_at_high_effort / 60, 1)} minutes at high intensity (over {round(high_effort_threshold)} bpm).")

    # Example: Analyze Speed/Pacing
    if 'velocity_smooth' in stream_data and stream_data['velocity_smooth']:
        speed_data = [v * 3.6 for v in stream_data['velocity_smooth']] # Convert m/s to km/h
        max_speed = max(speed_data)
        avg_speed = sum(speed_data) / len(speed_data)
        
        analysis_results.append(f"Speed Analysis for '{activity_name}':")
        analysis_results.append(f"  - Max Speed: {max_speed:.1f} km/h")
        analysis_results.append(f"  - Avg Speed: {avg_speed:.1f} km/h")
        # Add more sophisticated pacing analysis here if needed

    # Example: Altitude gain/loss
    if 'altitude' in stream_data and stream_data['altitude']:
        alt_data = stream_data['altitude']
        total_climb = 0
        for i in range(1, len(alt_data)):
            if alt_data[i] > alt_data[i-1]:
                total_climb += (alt_data[i] - alt_data[i-1])
        analysis_results.append(f"Altitude Analysis for '{activity_name}':")
        analysis_results.append(f"  - Estimated total climb (from streams): {int(total_climb)} meters (Note: This might differ from Strava's summary due to smoothing/algorithm).")


    if not analysis_results:
        return f"No specific analysis could be performed for {activity_name} with the available stream data."

    return "\n".join(analysis_results)