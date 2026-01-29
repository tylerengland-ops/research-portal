from datetime import datetime
import streamlit as st

# This creates a shared dictionary that persists across all users
# It lives in the server memory, not the user session
@st.cache_resource
def get_usage_tracker():
    return {}

def get_limit_config(client_id):
    """
    Returns (limit, period_type) based on client_id.
    period_type can be 'hour' or 'day'.
    """
    # 1. SPECIAL RULES: Demo accounts (30 per hour)
    if client_id in ["demo", "demo2"]:
        return 30, "hour"
    
    # 2. DEFAULT RULE: Everyone else (300 per day)
    return 300, "day"

def check_and_update_limit(client_id):
    """
    Checks rate limit and increments if allowed.
    Returns: (is_allowed, current_count, max_limit, period_name)
    """
    tracker = get_usage_tracker()
    limit, period_type = get_limit_config(client_id)
    
    now = datetime.now()
    
    # Generate the time key based on the period type
    if period_type == "hour":
        # Key changes every hour (e.g., "demo_2023-10-27_14")
        # This resets automatically when the hour changes
        time_key = now.strftime("%Y-%m-%d_%H")
    else:
        # Key changes every day (e.g., "alpha_2023-10-27")
        # This resets automatically at midnight
        time_key = now.strftime("%Y-%m-%d")
        
    # Unique storage key combining client and time
    storage_key = f"{client_id}_{time_key}"

    # Initialize counter if it doesn't exist
    if storage_key not in tracker:
        tracker[storage_key] = 0

    # Check limit
    if tracker[storage_key] >= limit:
        return False, tracker[storage_key], limit, period_type
    
    # Increment and allow
    tracker[storage_key] += 1
    return True, tracker[storage_key], limit, period_type
