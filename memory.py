# memory.py
# Handles long-term conversation storage and retrieval.

import json
import os
from typing import List, Dict

MEMORY_DIR = "conversation_memory"
MAX_HISTORY_LENGTH = 10 # Keep the last 5 user messages and 5 AI responses

def get_conversation_history(user_id: str) -> List[Dict[str, str]]:
    """Retrieves the last N turns of a user's conversation."""
    if not os.path.exists(MEMORY_DIR):
        os.makedirs(MEMORY_DIR)
        
    history_file = os.path.join(MEMORY_DIR, f"{user_id}.json")
    
    if not os.path.exists(history_file):
        return []
        
    with open(history_file, 'r') as f:
        history = json.load(f)
        return history[-MAX_HISTORY_LENGTH:]

def update_conversation_history(user_id: str, user_query: str, ai_response: str):
    """Adds the latest exchange to the user's conversation history."""
    history = get_conversation_history(user_id)
    
    history.append({"role": "user", "content": user_query})
    history.append({"role": "assistant", "content": ai_response})
    
    # Prune the history to keep it from growing indefinitely
    history_to_save = history[-MAX_HISTORY_LENGTH:]
    
    history_file = os.path.join(MEMORY_DIR, f"{user_id}.json")
    with open(history_file, 'w') as f:
        json.dump(history_to_save, f, indent=2)