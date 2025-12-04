# app.py
# This is the main FastAPI backend for the Fitness Coach app.
# It integrates with Strava API and uses Google Gemini for agentic coaching.
# Run with: uvicorn app:app --reload

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import os
import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool
# Removed 'Part' from imports because it causes an error in your version
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

# --- Tool Execution Map ---
# This links the "simple" names Gemini sees to the "real" functions in tools.py
GEMINI_TOOL_MAP = {
    "my_recent_activities": get_recent_activities_summary,
    "analyze_ride": analyze_specific_ride_depth,
    "my_progression": check_progression,
    "update_stats": update_user_physical_stats
}

# --- Agent/Tool Setup ---

def create_gemini_chat(user_id: str, history: list):
    """
    Creates a Gemini ChatSession with tools bound to the specific user_id.
    """
    
    # 1. Define the tools with docstrings (Gemini reads these to know what to do)
    def my_recent_activities():
        """Get a summary of my activities from the last 14 days, including ID, distance, and intensity."""
        pass 

    def analyze_ride(activity_id: int):
        """Analyze a specific ride in detail (using streams like HR, cadence) given its ID."""
        pass

    def my_progression():
        """Check if my training volume/intensity is increasing or decreasing compared to last month."""
        pass
    
    def update_stats(weight_kg: float = None, ftp: int = None):
        """Update my physical stats (weight in kg, FTP in watts)."""
        pass

    # 2. Bundle them up
    tools = [my_recent_activities, analyze_ride, my_progression, update_stats]
    
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
        model_name='gemini-2.5-flash', # Or 'gemini-2.0-flash-exp' if available
        tools=tools,
        system_instruction=system_instruction
    )
    
    # Convert history format (OpenAI -> Gemini)
    gemini_history = []
    for turn in history:
        role = "user" if turn["role"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [turn["content"]]})

    return model.start_chat(history=gemini_history)


# --- API Endpoints ---

@app.post("/coach")
async def coach_session(query: UserQuery):
    try:
        # 1. Init Chat
        conversation_history = get_conversation_history(query.user_id)
        chat = create_gemini_chat(query.user_id, conversation_history)
        
        current_content = query.voice_transcript
        ai_text = "I'm sorry, I couldn't process your request."

        # 2. Manual Tool Calling Loop (ReAct Pattern)
        for _ in range(10): # Max 10 turns to prevent infinite loops
            
            # Send message to model
            response = chat.send_message(current_content)
            
            # Check if model wants to call a function
            # In the Python SDK, function_call is inside parts[0]
            if response.parts[0].function_call:
                
                # Get call details
                fc = response.parts[0].function_call
                tool_name = fc.name
                tool_args = dict(fc.args)
                
                print(f"🤖 Agent requesting tool: {tool_name} with args: {tool_args}")
                
                # Find actual function
                func_to_run = GEMINI_TOOL_MAP.get(tool_name)
                
                if func_to_run:
                    try:
                        # Inject user_id since our backend functions need it
                        result = func_to_run(user_id=query.user_id, **tool_args)
                    except Exception as e:
                        result = f"Error executing {tool_name}: {str(e)}"
                else:
                    result = f"Error: Tool {tool_name} not found."

                # Send result back to model
                # FIX: Using dictionary format compatible with your installed SDK
                current_content = {
                    "role": "function",
                    "parts": [
                        {
                            "function_response": {
                                "name": tool_name,
                                "response": {"result": result}
                            }
                        }
                    ]
                }
                # The loop continues; we send this content back to chat.send_message
                
            else:
                # No function call -> Final text response
                ai_text = response.text
                break
        
        # 3. Save & Return
        update_conversation_history(query.user_id, query.voice_transcript, ai_text)
        return {"advice": ai_text}
        
    except Exception as e:
        print(f"Error in coach_session: {e}")
        # Return error as normal text so the client doesn't crash
        return {"advice": f"I encountered an error: {str(e)}"}

@app.get("/health")
async def health_check():
    return {"status": "Running"}

# --- Strava Auth ---
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