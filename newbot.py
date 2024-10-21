from flask import Flask, request, jsonify, render_template, make_response
from flask_cors import CORS
import os
from openai import OpenAI
from dotenv import load_dotenv
import pymysql
import uuid
import requests
import time

load_dotenv()

key = os.getenv("OPENAI_API_KEY")
assistant_id_berater = os.getenv("ASSISTANT_ID_berater")

client = OpenAI(api_key=key)
app = Flask(__name__)
# Enable CORS with credentials to allow cross-site requests
CORS(app, supports_credentials=True, origins=["https://probenahmeprotokoll.de", "https://erdbaron.com"])

# Dictionary to store session data (thread IDs and user details)
session_data = {}

# Variables to manage tokens for Zoho API (use your actual values)
access_token = "1000.821b23d0f8dcafeb213626d51d6e9459.59a1c8eaabf2b3a9ae4e4e1d866491ec"
refresh_token = "1000.259787181a80f3211fb817478fc79939.8db39ac9cf076db3e98573cc678f1b87"
token_expires_in = 3600  # Time in seconds for token expiration (initially 3600)
token_last_refresh_time = time.time()

# Function to refresh the access token using the refresh token
def refresh_access_token():
    global access_token, token_last_refresh_time, token_expires_in
    
    url = "https://accounts.zoho.eu/oauth/v2/token"  # Replace with your region-specific Zoho token endpoint
    
    payload = {
        'refresh_token': refresh_token,
        'client_id': '1000.ACVWWHZHYUKV53ZYWS3LG367BQYKTH',  # Replace with your client ID
        'client_secret': '9eb75a2b58c010a674e37be778409967f73f5215c7',  # Replace with your client secret
        'grant_type': 'refresh_token'
    }

    response = requests.post(url, params=payload)
    if response.status_code == 200:
        response_data = response.json()
        access_token = response_data['access_token']
        token_expires_in = response_data.get('expires_in', 3600)
        token_last_refresh_time = time.time()
        print(f"Access token refreshed: {access_token}")
    else:
        print(f"Failed to refresh access token: {response.text}")
        raise Exception("Failed to refresh access token")

def ensure_valid_access_token():
    global token_last_refresh_time, token_expires_in
    current_time = time.time()
    if current_time - token_last_refresh_time >= token_expires_in:
        refresh_access_token()


def extract_details_from_summary(summary):
    try:
        print(f"Extracting details from summary:\n{summary}")
        details = {}
        # Define the mapping of possible field names to their keys
        field_mapping = {
            'Anrede': 'salutation',
            'Vorname': 'first_name',
            'Nachname': 'last_name',
            'Email': 'email',
            'Telefon': 'phone',
            'Postleitzahl': 'zip_code',
#            'Geplanter Start': 'planned_start',
            'Menge': 'quantity',
            'Beschreibung': 'description',
            'Betreff': 'subject'  # If needed
        }
        # Split the summary into lines
        lines = summary.splitlines()
        # Process each line
        for line in lines:
            line = line.strip()
            if not line:
                continue  # Skip empty lines
            # Check if the line contains a colon
            if ':' in line:
                # Split the line into potential field name and value
                field_name_part, value = line.split(':', 1)
                # Clean up the field name
                field_name = field_name_part.strip().strip('-').strip().strip('**').strip()
                value = value.strip()
                # Map the field name to our internal key
                key = field_mapping.get(field_name)
                if key:
                    details[key] = value
                    print(f"Extracted {key}: {value}")
                else:
                    print(f"Ignored unrecognized field: {field_name}")
            else:
                print(f"Ignored line without colon: {line}")
        # Check if all necessary fields are present
        required_fields = ['first_name', 'last_name', 'email', 'phone', 'zip_code', 'quantity', 'description']
        if all(field in details for field in required_fields):
            print("Parsed Details:", details)
            return details
        else:
            missing_fields = [field for field in required_fields if field not in details]
            print(f"Error: Not all details were extracted correctly. Missing fields: {missing_fields}")
            return None
    except Exception as e:
        print(f"Error extracting details from summary: {e}")
        return None

def send_to_zoho(user_details):
    try:
        ensure_valid_access_token()  # Ensure the access token is valid before making the request

        zoho_url = "https://www.zohoapis.eu/crm/v3/Deals"  # Endpoint for creating a deal

        headers = {
            'Authorization': f'Zoho-oauthtoken {access_token}',
            'Content-Type': 'application/json',
        }

        # Extract details from user_details
        first_name = user_details.get('first_name', '')
        last_name = user_details.get('last_name', '')
        phone = user_details.get('phone', '')
        zip_code = user_details.get('zip_code', '')
        description = user_details.get('description', '')
        email = user_details.get('email', '')
       # planned_start = user_details.get('planned_start', '')
        quantity = user_details.get('quantity', '')
        subject = user_details.get('subject', '')

        # Generate Deal_Name using first and last name
        deal_name = f"Deal with {first_name} {last_name}"

        # Default pipeline value (replace with the actual pipeline expected by your CRM)
        pipeline_value = "Standard"  # Replace with valid pipeline name in your Zoho CRM
        stage_value = "Erstellt"  # Replace with valid stage in the pipeline

        # Construct the data payload
        data = {
            "data": [
                {
                    "Deal_Name": deal_name,
                    "Vorname": first_name,
                    "Nachname": last_name,
                    "Mobil": phone,
                    "Postleitzahl_Temp": zip_code,
                    "Description": description,
                    "E_Mail": email,
              #      "Geplanter_Start": planned_start,
                    "Gesch_tzte_Menge_m": quantity,
                    "Betreff": subject,
                    "Pipeline": pipeline_value,
                    "Stage": stage_value,
                    # Add other fields as needed
                    "Lead_Source": "Chatbot"
                }
            ]
        }

        # Make the POST request to Zoho CRM
        response = requests.post(zoho_url, json=data, headers=headers)
        if response.status_code == 401:  # If unauthorized, refresh token and retry once
            refresh_access_token()
            headers['Authorization'] = f'Zoho-oauthtoken {access_token}'
            response = requests.post(zoho_url, json=data, headers=headers)

        if response.status_code in [200, 201]:
            print("Data successfully sent to Zoho CRM.")
            print("Response:", response.json())
        else:
            print(f"Failed to send data to Zoho CRM. Status Code: {response.status_code}")
            print("Response:", response.text)

    except Exception as e:
        print(f"Error while sending to Zoho: {e}")

# Function to connect to the MySQL database
def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASS'),
        database=os.getenv('DB_NAME'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# Function to log chat data into the database
def log_chat(thread_id, user_message, assistant_response):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO chatlog (thread_id, user_message, assistant_response) VALUES (%s, %s, %s)"
            cursor.execute(sql, (thread_id, user_message, assistant_response))
            connection.commit()
    except Exception as e:
        print(f"Error inserting into the database: {e}")
    finally:
        connection.close()

@app.route("/askberater", methods=["POST"])
def ask1():
    print("Received request at /askberater")
    user_message = request.json.get("message", "")
    print(f"User message: {user_message}")
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
        session_data[session_id] = {
            'thread': client.beta.threads.create(),
            'user_details': {},
            'summary': None
        }
        print(f"New session created with ID: {session_id}")
    elif session_id not in session_data:
        session_data[session_id] = {
            'thread': client.beta.threads.create(),
            'user_details': {},
            'summary': None
        }
        print(f"Session data initialized for existing session ID: {session_id}")
    thread_id = session_data[session_id]['thread'].id
    print(f"Using thread ID: {thread_id}")
    client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread_id, assistant_id=assistant_id_berater)
    messages = list(client.beta.threads.messages.list(
        thread_id=thread_id, run_id=run.id))
    response_message = messages[0].content[0].text.value
    print(f"Response from OpenAI: {response_message}")
    # Store the summary for confirmation if present
    if "zusammenfassung" in response_message.lower():
        session_data[session_id]['summary'] = response_message
        print(f"Summary stored: {session_data[session_id]['summary']}")
    # If user confirms the summary, process it
    if "yes this is correct" in user_message.lower() or "this is correct" in user_message.lower():
        confirmed_summary = session_data[session_id].get('summary')
        if confirmed_summary:
            print(f"Confirmed Summary: {confirmed_summary}")
            user_details = extract_details_from_summary(confirmed_summary)
            if user_details:
                session_data[session_id]['user_details'] = user_details
                # Print session data for debugging
                print("Parsed User Details:", user_details)
                print("Session Data:", session_data[session_id])
                # Send data to Zoho CRM
                send_to_zoho(user_details)
            else:
                print("Failed to parse user details from the summary.")
        else:
            print("No summary found to confirm.")
    response = make_response(jsonify(
        {"response": response_message, "thread_id": thread_id}))
    response.set_cookie('session_id', session_id,
                        httponly=True, samesite='None', secure=True)
    return response


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)
