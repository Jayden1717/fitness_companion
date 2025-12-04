# chat_client.py
import requests
import json
import os

# Configuration for your FastAPI backend
BASE_URL = "http://127.0.0.1:8000"
COACH_ENDPOINT = "/coach"
DEFAULT_USER_ID = "user123" # Use the same user_id as in your app.py's user_tokens

def send_message_to_coach(user_id: str, message: str) -> str:
    """Sends a message to the FastAPI /coach endpoint and returns the AI's advice."""
    url = f"{BASE_URL}{COACH_ENDPOINT}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "user_id": user_id,
        "voice_transcript": message
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        return response.json().get("advice", "Error: No advice received from coach.")
    except requests.exceptions.ConnectionError:
        return "Error: Could not connect to the coach API. Is the backend running?"
    except requests.exceptions.HTTPError as http_err:
        try:
            error_details = response.json()
            return f"HTTP error occurred: {http_err} - Details: {error_details.get('detail', 'No specific detail.')}"
        except json.JSONDecodeError:
            return f"HTTP error occurred: {http_err} - Response: {response.text}"
    except Exception as err:
        return f"An unexpected error occurred: {err}"

def chat_interface():
    print("--- Crank'd AI Coach Chat Interface ---")
    print(f"Talking to user_id: {DEFAULT_USER_ID}")
    print("Type your message and press Enter. Type 'exit' or 'quit' to end the chat.")
    print("-" * 35)

    while True:
        user_input = input("\nYou (or type 'exit'): ")
        if user_input.lower() in ["exit", "quit"]:
            print("Ending chat. Goodbye!")
            break
        
        print("\nCrank'd is thinking...")
        coach_advice = send_message_to_coach(DEFAULT_USER_ID, user_input)
        print(f"\nCrank'd: {coach_advice}")

if __name__ == "__main__":
    chat_interface()