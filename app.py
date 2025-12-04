# app.py
# This is the main FastAPI backend for the Fitness Coach app.
# It integrates with Strava API and uses Google Gemini for agentic coaching.
# Run with: uvicorn app:app --reload

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import os
import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool
from dotenv import load_dotenv
from functools import partial

# Import our modules
from memory import get_conversation_history, update_conversation_history
from tools import (
    get_recent_activities_summary, 
    analyze_specific_ride_depth, 
    check_progression, 
    update_user_physical_stats
)
# We still need the strava auth callback logic, though some is now in strava_client
from strava_client import user_tokens, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, get_access_token
import requests

load_dotenv()

app = FastAPI(title="Fitness Coach API (Gemini Agent)")

# --- Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY in .env file.")

genai.configure(api_key=GEMINI_API_KEY)

# --- Pydantic Models ---
class UserQuery(BaseModel):
    user_id: str
    voice_transcript: str

# --- Agent/Tool Setup ---

def create_gemini_chat(user_id: str, history: list):
    """
    Creates a Gemini ChatSession with tools bound to the specific user_id.
    """
    # Create partial functions that already have user_id filled in.
    # The LLM sees a function signature without user_id.
    
    def my_recent_activities():
        """Get a summary of my activities from the last 14 days, including ID, distance, and intensity."""
        return get_recent_activities_summary(user_id)

    def analyze_ride(activity_id: int):
        """Analyze a specific ride in detail (using streams like HR, cadence) given its ID."""
        return analyze_specific_ride_depth(user_id, activity_id)

    def my_progression():
        """Check if my training volume/intensity is increasing or decreasing compared to last month."""
        return check_progression(user_id)
    
    def update_stats(weight_kg: float = None, ftp: int = None):
        """Update my physical stats (weight in kg, FTP in watts)."""
        return update_user_physical_stats(user_id, weight_kg, ftp)

    # Define the toolset
    tools = [my_recent_activities, analyze_ride, my_progression, update_stats]
    
    # System Instruction
    system_instruction = """
    You are Crank'd, an expert AI cycling coach. 
    Your goal is to help the user improve their fitness using their Strava data.
    
    Capabilities:
    1. Always start by understanding the user's intent.
    2. USE YOUR TOOLS to fetch data. Do not guess. 
    3. If the user asks "how did I do?", fetch recent activities first.
    4. If a user asks about a specific ride, look at the summary list to find the ID, then use 'analyze_ride' with that ID.
    5. Calculate metrics like W/kg if you have the data. If user weight is missing and needed, ask for it nicely.
    6. Be concise, motivating, and specific. Use metric units (km, meters).
    """

    model = genai.GenerativeModel(
        model_name='gemini-1.5-flash',
        tools=tools,
        system_instruction=system_instruction
    )
    
    # Convert history format (OpenAI -> Gemini)
    # OpenAI: {'role': 'user', 'content': '...'}
    # Gemini: {'role': 'user', 'parts': ['...']}
    gemini_history = []
    for turn in history:
        role = "user" if turn["role"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [turn["content"]]})

    return model.start_chat(history=gemini_history)


# --- API Endpoints ---

@app.post("/coach")
async def coach_session(query: UserQuery):
    try:
        # 1. Retrieve Memory
        conversation_history = get_conversation_history(query.user_id)
        
        # 2. Initialize Agent with Tools
        chat = create_gemini_chat(query.user_id, conversation_history)
        
        # 3. Send Message (Handles tool calling loop automatically)
        response = chat.send_message(query.voice_transcript)
        
        # 4. Extract Text Response
        ai_text = response.text
        
        # 5. Update Memory
        update_conversation_history(query.user_id, query.voice_transcript, ai_text)
        
        return {"advice": ai_text}
        
    except Exception as e:
        print(f"Error in coach_session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "Running", "model": "gemini-1.5-flash"}

# --- Strava Auth (Legacy/Callback) ---
@app.get("/strava/callback")
async def strava_callback(request: Request):
    code = request.query_params.get("code")
    user_id = request.query_params.get("user_id") or "user123" 
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    token_url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code"
    }
    try:
        response = requests.post(token_url, data=payload)
        response.raise_for_status()
        tokens = response.json()
        
        # Update our in-memory store (via reference in strava_client if we imported it, 
        # or just modify the dict since we imported it from there)
        user_tokens[user_id] = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_at": tokens["expires_at"]
        }
        return {"status": "Authenticated", "user_id": user_id}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Strava auth failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)