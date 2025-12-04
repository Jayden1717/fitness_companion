import json
import os

PROFILE_FILE = "user_profiles.json"

def get_user_profile(user_id: str):
    if not os.path.exists(PROFILE_FILE):
        return {}
    
    with open(PROFILE_FILE, "r") as f:
        profiles = json.load(f)
        return profiles.get(user_id, {})

def update_user_profile(user_id: str, weight_kg: float = None, ftp: int = None):
    profiles = {}
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, "r") as f:
            profiles = json.load(f)
    
    if user_id not in profiles:
        profiles[user_id] = {}
    
    if weight_kg: profiles[user_id]["weight_kg"] = weight_kg
    if ftp: profiles[user_id]["ftp"] = ftp
    
    with open(PROFILE_FILE, "w") as f:
        json.dump(profiles, f, indent=2)
    
    return profiles[user_id]
