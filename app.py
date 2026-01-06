"""
Full-Context Research Mining Portal
A multi-tenant Streamlit application for analyzing qualitative research transcripts
using Gemini's large context window.
"""

# --- SAFE IMPORT BLOCK ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass # If we are on the cloud and dotenv is missing, just skip it!
# -------------------------
import streamlit as st
import os
import json
import io
from typing import Dict, List, Tuple
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import docx

# ============================================================================
# CONFIGURATION
# ============================================================================

# Multi-tenant client database: Maps client_id to Google Drive Folder ID
# Load database securely from Streamlit Secrets
CLIENT_DATABASE = st.secrets["client_database"]

# ============================================================================
# STYLING - Hide Streamlit UI elements for embed-friendly widget appearance
# ============================================================================

def apply_custom_styling():
    """Apply custom CSS to create a clean, widget-like interface"""
    st.markdown("""
        <style>
        /* 1. Hide the Streamlit Header (The colorful bar at top) */
        header {visibility: hidden;}
        
        /* 2. Hide the "Made with Streamlit" Footer */
        .stApp > header {display: none;}
        footer {visibility: hidden;}
        #MainMenu {visibility: hidden;} /* This hides the hamburger menu */
        
        /* 3. Aggressively hide the specific footer container */
        .stFooter {display: none;}
        
        /* Clean container styling */
        .stApp {
            max-width: 100%;
        }
        
        /* Status indicator styling */
        .status-indicator {
            background-color: #f0f2f6;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #4CAF50;
        }
        
        .status-indicator h4 {
            margin: 0;
            color: #1f1f1f;
            font-size: 14px;
        }
        
        .status-indicator p {
            margin: 5px 0 0 0;
            color: #666;
            font-size: 12px;
        }
        
        /* Chat message styling */
        .stChatMessage {
            padding: 10px;
            margin: 5px 0;
        }
        </style>
    """, unsafe_allow_html=True)

# ============================================================================
# GOOGLE DRIVE INTEGRATION
# ============================================================================

def get_drive_service():
    """
    Create and return an authenticated Google Drive service instance
    using the service account credentials from environment variable.
    """
    try:
        # Load service account credentials from environment variable
        service_account_info = json.loads(os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '{}'))
        
        if not service_account_info:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable is not set or empty")
        
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        
        service = build('drive', 'v3', credentials=credentials)
        return service
    except Exception as e:
        st.error(f"Failed to authenticate with Google Drive: {str(e)}")
        return None

def list_files_in_folder(service, folder_id: str) -> List[Dict]:
    """
    Recursively list all files in a Google Drive folder and its subfolders.
    Returns a list of file dictionaries with 'id', 'name', and 'mimeType'.
    """
    all_files = []
    
    try:
        # Query for files in the current folder
        query = f"'{folder_id}' in parents and trashed=false"
        results = service.files().list(
            q=query,
            fields="files(id, name, mimeType)",
            pageSize=1000
        ).execute()
        
        items = results.get('files', [])
        
        for item in items:
            # If it's a folder, recursively get its contents
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                all_files.extend(list_files_in_folder(service, item['id']))
            else:
                all_files.append(item)
        
        return all_files
    except Exception as e:
        st.error(f"Error listing files in folder: {str(e)}")
        return []

def download_file_content(service, file_id: str, mime_type: str) -> str:
    """
    Download and return the text content of a file from Google Drive.
    Supports .txt, .csv, and .docx files.
    """
    try:
        # Handle Google Docs export
        if mime_type == 'application/vnd.google-apps.document':
            request = service.files().export_media(fileId=file_id, mimeType='text/plain')
        else:
            request = service.files().get_media(fileId=file_id)
        
        # Download file content
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        file_stream.seek(0)
        
        # Parse content based on file type
        if mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            # Parse .docx file
            doc = docx.Document(file_stream)
            return '\n'.join([paragraph.text for paragraph in doc.paragraphs])
        else:
            # Parse .txt, .csv, or exported Google Doc
            return file_stream.read().decode('utf-8', errors='ignore')
    
    except Exception as e:
        return f"[Error reading file: {str(e)}]"

def load_client_data(client_id: str) -> Tuple[str, int]:
    """
    Load all transcript data for a given client from their Google Drive folder.
    Returns (full_transcript_context, file_count)
    """
    if client_id not in CLIENT_DATABASE:
        return "", 0
    
    folder_id = CLIENT_DATABASE[client_id]
    service = get_drive_service()
    
    if not service:
        return "", 0
    
    # Get all files from the folder
    files = list_files_in_folder(service, folder_id)
    
    # Filter for supported file types
    supported_mimes = [
        'text/plain',
        'text/csv',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.google-apps.document'
    ]
    
    relevant_files = [f for f in files if f['mimeType'] in supported_mimes]
    
    # Download and combine all file contents
    combined_content = []
    for file in relevant_files:
        content = download_file_content(service, file['id'], file['mimeType'])
        combined_content.append(f"=== FILE: {file['name']} ===\n{content}\n")
    
    full_transcript_context = "\n\n".join(combined_content)
    
    return full_transcript_context, len(relevant_files)

# ============================================================================
# GEMINI AI INTEGRATION
# ============================================================================

def initialize_gemini():
    """Initializes the Gemini model with the API key."""
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            st.error("GEMINI_API_KEY not found in environment variables")
            return None
        
        # Configure the library
        genai.configure(api_key=api_key)
        
        # Initialize the model
        model = genai.GenerativeModel('gemini-2.5-flash')
        return model
    except Exception as e:
        st.error(f"Failed to initialize AI model: {str(e)}")
        return None

def generate_response(client, full_context: str, user_query: str, chat_history: list, custom_persona: str = "", temperature: float = 0.2):
    """
    Generate a response using the selected Gemini model, including chat history.
    """
    # 1. Build the Persona
    base_persona = """You are an expert Research Analyst (not an Interviewer). You have access to the COMPLETE dataset.
    CRITICAL INSTRUCTIONS:
    - Scan the ENTIRE text for counts.
    - Cite specific quotes where helpful.
    - If you cannot find info, state that.
    - If asked for a count, you MUST scan the ENTIRE text to find EVERY instance.
    - Do not estimate.
    - List the specific quotes or participants if possible to verify your count."""

    if custom_persona:
        system_persona = f"{base_persona}\n\nADDITIONAL CONTEXT:\n{custom_persona}"
    else:
        system_persona = base_persona
    
    # 2. Format Chat History (The Memory)
    # We skip the last message because that is the current user_query which we add at the end
    history_text = ""
    # Safe check: ensure chat_history is a list
    if isinstance(chat_history, list):
        for msg in chat_history[:-1]: 
            role = "User" if msg["role"] == "user" else "Research Analyst"
            content = msg.get("content", "")
            history_text += f"{role}: {content}\n\n"

    # 3. Build the Prompt (Now including the history!)
    prompt = f"""{system_persona}

=== COMPLETE RESEARCH DATA ===
{full_context}

=== CONVERSATION HISTORY ===
{history_text}

=== CURRENT USER QUESTION ===
{user_query}
"""
    
    try:
        # 4. Configure the "Creativity" (Temperature)
        config = genai.types.GenerationConfig(temperature=temperature)

        # 5. Send to AI
        response = client.generate_content(prompt, generation_config=config)
        return response.text

    except Exception as e:
        return f"Error generating response: {str(e)}"


# ============================================================================
# AUTHENTICATION & SESSION MANAGEMENT
# ============================================================================

def authenticate_client():
    """
    Handle client authentication via URL parameter or manual input.
    Returns the authenticated client_id or None.
    """
    # Check for URL parameter
    query_params = st.query_params
    client_id = query_params.get('client_id', None)
    
    if client_id and client_id in CLIENT_DATABASE:
        return client_id
    
    # If no valid URL parameter, show manual login
    st.title("🔐 Research Portal Access")
    st.write("Please enter your Access ID to continue.")
    
    access_id = st.text_input("Access ID", type="password")
    
    if access_id:
        if access_id in CLIENT_DATABASE:
            return access_id
        else:
            st.error("Invalid Access ID. Please check your credentials.")
    
    return None

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point"""
    
    # Apply custom styling
    apply_custom_styling()
    
    # Set page configuration
    st.set_page_config(
        page_title="Research Portal",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Initialize session state
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'client_id' not in st.session_state:
        st.session_state.client_id = None
    if 'full_context' not in st.session_state:
        st.session_state.full_context = ""
    if 'file_count' not in st.session_state:
        st.session_state.file_count = 0
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'custom_persona' not in st.session_state:
        st.session_state.custom_persona = ""
    if 'query_count' not in st.session_state:
        st.session_state.query_count = 0
    
    # Authentication
    if not st.session_state.authenticated:
        client_id = authenticate_client()
        if client_id:
            st.session_state.client_id = client_id
            st.session_state.authenticated = True
            
            # Load client data
            with st.spinner("Loading your research data..."):
                full_context, file_count = load_client_data(client_id)
                st.session_state.full_context = full_context
                st.session_state.file_count = file_count
            
            st.rerun()
        else:
            st.stop()
    

    # Main application interface
    # 1. Display branded logo
    st.image("Q360 Logo.png", width=70)  # <--- Change filename/width as needed

    # 2. Title 
    st.title("Research Analysis Portal")
    
    # Status indicator
    st.markdown(f"""
        <div class="status-indicator">
            <p>
                <strong>Database:</strong> {st.session_state.file_count} files | 
                <strong>Context:</strong> {len(st.session_state.full_context):,} characters
            </p>
            <p style="margin-top: 8px; opacity: 0.8; font-size: 0.9em;">
                <em>⚠️Note: Exploratory tool—verify critical data. This chat is designed to be thorough and may take a few moments per request.</em>
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    # Optional: Custom persona training
    with st.expander("⚙️ Advanced Settings (Optional)"):
        st.session_state.custom_persona = st.text_area(
            "Additional AI Training Instructions",
            value=st.session_state.custom_persona,
            help="Add custom instructions to further train the AI's analysis approach",
            height=100
        )
    
        temperature = st.slider(
            "Creativity (Temperature)",
            min_value=0.0,
            max_value=1.0,
            value=0.2,
            step=0.1,
            help="0.0 = Precise/Math. 1.0 = Creative."
        )
        # -----------------------

    # Chat interface
    st.subheader("💬 Ask Questions About The Data")
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Ask a question about the research data..."):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # --- SMART LIMIT LOGIC ---
        # 1. Define the limit specifically for the 'demo' user
        DEMO_LIMIT = 15
        is_demo_user = (st.session_state.client_id == "demo")
        limit_reached = False
        
        # 2. Check if this specific user has hit the limit
        if is_demo_user and st.session_state.query_count >= DEMO_LIMIT:
            limit_reached = True
            
        # 3. Enforce the limit
        if limit_reached:
            with st.chat_message("assistant"):
                st.error(f"🔒 Demo Limit Reached ({DEMO_LIMIT}/{DEMO_LIMIT}). Please contact us for full access.")
        else:
            # Generate AI response (Normal flow)
            with st.chat_message("assistant"):
                with st.spinner("Analyzing complete dataset..."):
                    client = initialize_gemini()
                    if client:
                        response = generate_response(
                            client,
                            st.session_state.full_context,
                            prompt,
                            st.session_state.messages,
                            st.session_state.custom_persona,
                            temperature=temperature
                        )
                        
                        st.markdown(response)
                        st.session_state.messages.append({"role": "assistant", "content": response})
                        
                        # Increment counter
                        st.session_state.query_count += 1
                        
                        st.rerun()
                    else:
                        st.error("Failed to initialize AI model. Please check you configuration.")

if __name__ == "__main__":
    main()
