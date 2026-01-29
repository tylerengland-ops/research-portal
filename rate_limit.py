# ... existing code ...
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import docx

# --- PASTE THIS NEW LINE HERE ---
from rate_limit import check_and_update_limit
# --------------------------------

import os
import toml 
# ... existing code ...
