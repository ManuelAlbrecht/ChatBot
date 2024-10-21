from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import os
from openai import OpenAI
from dotenv import load_dotenv
import uuid
import requests
import time
import sys

load_dotenv()

# Get credentials from environment variables
key = os.getenv("OPENAI_API_KEY")
assistant_id_berater = os.getenv("ASSISTANT_ID_berater")

# Zoho CRM credentials from environment variables
access_token = '1000.821b23d0f8dcafeb213626d51d6e9459.59a1c8eaabf2b3a9ae4e4e1d866491ec'
refresh_token = '1000.259787181a80f3211fb817478fc79939.8db39ac9cf076db3e98573cc678f1b87'
client_id = '1000.ACVWWHZHYUKV53ZYWS3LG367BQYKTH'
client_secret = '9eb75a2b58c010a674e37be778409967f73f5215c7'
token_expires_in = 3600
token_last_refresh_time = time.time()

client = OpenAI(api_key=key)
app = Flask(__name__)

# Enable CORS for your domains
CORS(app, supports_credentials=True, origins=["https://probenahmeprotokoll.de", "https://erdbaron.com"])

session_data = {}

# Log versions for debugging
print(f"Python version: {sys.version}")
print(f"Requests version: {requests.__version__}")
print(f"OpenAI version: {client.version}")

def refresh_access_token():
    global access_token, token_last_refresh_time, token_expires_in
    try:
        url = "https://accounts.zoho.eu/oauth/v2/token"
        payload = {
            'refresh_token': refresh_token,
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'refresh_token'
        }
        response = requests.post(url, params=payload)
        if response.status_code == 200:
            response_data = response.json()
            access_token = response_data['access_token']
            token_expires_in = int(response_data.get('expires_in', 3600))
            token_last_refresh_time = time.time()
            print("Access token refreshed.")
        else:
            print(f"Failed to refresh access token: {response.text}")
            raise Exception("Failed to refresh access token")
    except Exception as e:
        print(f"Exception in refresh_access_token: {e}")
        import traceback
        traceback.print_exc()

def ensure_valid_access_token():
    global token_last_refresh_time, token_expires_in
    try:
        current_time = time.time()
        if current_time - token_last_refresh_time >= token_expires_in:
            refresh_access_token()
    except Exception as e:
        print(f"Exception in ensure_valid_access_token: {e}")
        import traceback
        traceback.print_exc()

def extract_details_from_summary(summary):
    try:
        print(f"Extracting details from summary:\n{summary}")
        details = {}
        field_mapping = {
            'Anrede': 'salutation',
            'Vorname': 'first_name',
            'Nachname': 'last_name',
            'Email': 'email',
            'E-Mail': 'email',
            'Telefon': 'phone',
            'Handynummer': 'phone',
            'Postleitzahl': 'zip_code',
            'PLZ': 'zip_code',
            'Menge': 'quantity',
            'Beschreibung': 'description',
            'Betreff': 'subject'
        }
        lines = summary.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if ':' in line:
                field_name_part, value = line.split(':', 1)
                field_name = field_name_part.strip().strip('-').strip().strip('**').strip()
                value = value.strip()
                key = field_mapping.get(field_name)
                if key:
                    details[key] = value
                    print(f"Extracted {key}: {value}")
                else:
                    print(f"Ignored unrecognized field: {field_name}")
            else:
                print(f"Ignored line without colon: {line}")
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
        import traceback
        traceback.print_exc()
        return None

def send_to_zoho(user_details):
    try:
        ensure_valid_access_token()
        zoho_url = "https://www.zohoapis.eu/crm/v3/Deals"

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
        quantity = user_details.get('quantity', '')
        subject = user_details.get('subject', '')

        deal_name = f"Deal with {first_name} {last_name}"
        pipeline_value = "Standard"
        stage_value = "Erstellt"

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
                    "Geschätzte_Menge_m³": quantity,
                    "Betreff": subject,
                    "Pipeline": pipeline_value,
                    "Stage": stage_value,
                    "Lead_Source": "Chatbot"
                }
            ]
        }

        print("Data being sent to Zoho CRM:", data)
        response = requests.post(zoho_url, json=data, headers=headers)
        print(f"Zoho CRM Response Status Code: {response.status_code}")
        print(f"Zoho CRM Response Text: {response.text}")
        if response.status_code == 401:
            refresh_access_token()
            headers['Authorization'] = f'Zoho-oauthtoken {access_token}'
            response = requests.post(zoho_url, json=data, headers=headers)

        if response.status_code in [200, 201]:
            print("Data successfully sent to Zoho CRM.")
            print("Response:", response.json())
        else:
            print(f"Failed to send data to Zoho CRM. Status Code: {response.status_code}")
            print("Error Response:", response.text)

    except Exception as e:
        print(f"Error while sending to Zoho: {e}")
        import traceback
        traceback.print_exc()

@app.route("/askberater", methods=["POST"])
def ask1():
    try:
        print("Received request at /askberater")
        user_message = request.json.get("message", "")
        print(f"User message: {user_message}")
        user_message_lower = user_message.lower()
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

        if "zusammenfassung" in response_message.lower():
            session_data[session_id]['summary'] = response_message
            print(f"Summary stored: {session_data[session_id]['summary']}")
        if any(phrase in user_message_lower for phrase in ["yes this is correct", "this is correct", "ja, das ist korrekt", "ja", "korrekt", "das ist korrekt"]):
            confirmed_summary = session_data[session_id].get('summary')
            if confirmed_summary:
                print(f"Confirmed Summary: {confirmed_summary}")
                user_details = extract_details_from_summary(confirmed_summary)
                if user_details:
                    session_data[session_id]['user_details'] = user_details
                    print("Parsed User Details:", user_details)
                    print("Session Data:", session_data[session_id])
                    send_to_zoho(user_details)
                    response_message = (f"Danke {user_details.get('first_name', '')}! "
                                        "Ihre Daten wurden erfolgreich übermittelt.")
                else:
                    print("Failed to parse user details from the summary.")
                    response_message = "Entschuldigung, es gab ein Problem beim Verarbeiten Ihrer Daten."
            else:
                print("No summary found to confirm.")
        else:
            # Continue the conversation
            pass

        response = make_response(jsonify(
            {"response": response_message, "thread_id": thread_id}))
        response.set_cookie('session_id', session_id,
                            httponly=True, samesite='None', secure=True)
        return response
    except Exception as e:
        print(f"Exception in ask1: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response": "Entschuldigung, ein Fehler ist aufgetreten."}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
