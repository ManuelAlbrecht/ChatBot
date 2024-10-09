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
CORS(app, supports_credentials=True, origins=["https://probenahmeprotokoll.de"])

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

# Zoho CRM API integration with Deal_Name, Pipeline, and Stage
def send_to_zoho(first_name, last_name, phone, zip_code, description):
    try:
        ensure_valid_access_token()  # Ensure the access token is valid before making the request

        zoho_url = "https://www.zohoapis.eu/crm/v3/Deals"  # Endpoint for creating a deal
        
        headers = {
            'Authorization': f'Zoho-oauthtoken {access_token}',
            'Content-Type': 'application/json',
        }

        # Generate Deal_Name using first and last name
        deal_name = f"Deal with {first_name} {last_name}"

        # Default pipeline value (replace with the actual pipeline expected by your CRM)
        pipeline_value = "Standard"  # Replace with valid pipeline
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
                    "Pipeline": pipeline_value,  # Pipeline must contain the Stage
                    "Stage": stage_value  # Add a valid stage within the pipeline
                }
            ]
        }

        # Make the POST request to Zoho CRM
        response = requests.post(zoho_url, json=data, headers=headers)
        if response.status_code == 401:  # If unauthorized, refresh token and retry once
            refresh_access_token()
            headers['Authorization'] = f'Zoho-oauthtoken {access_token}'
            response = requests.post(zoho_url, json=data, headers=headers)

        return response.json()
    except Exception as e:
        print(f"Error while sending to Zoho: {e}")
        return {"status": "error", "message": str(e)}

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

# Handle the chat functionality for POST requests
@app.route("/askberater", methods=["POST"])
def ask1():
    user_message = request.json.get("message").lower()
    
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
        session_data[session_id] = {
            'thread': client.beta.threads.create(),
            'step': None,
            'user_details': {}
        }
    elif session_id not in session_data:
        session_data[session_id] = {
            'thread': client.beta.threads.create(),
            'step': None,
            'user_details': {}
        }

    thread_id = session_data[session_id]['thread'].id

    # Trigger offer-making flow if the user expresses intent
    if "angebot machen" in user_message or "ich möchte ein angebot" in user_message:
        session_data[session_id]['step'] = "first_name"
        response_message = "Großartig! Beginnen wir mit Ihrem Vornamen. Wie lautet Ihr Vorname?"

    elif session_data[session_id]['step'] == "first_name":
        session_data[session_id]['user_details']['first_name'] = user_message
        session_data[session_id]['step'] = "last_name"
        response_message = "Danke schön! Wie lautet Ihr Nachname?"

    elif session_data[session_id]['step'] == "last_name":
        session_data[session_id]['user_details']['last_name'] = user_message
        session_data[session_id]['step'] = "phone"
        response_message = "Habe es! Was ist Ihre Telefonnummer?"

    elif session_data[session_id]['step'] == "phone":
        session_data[session_id]['user_details']['phone'] = user_message
        session_data[session_id]['step'] = "zip_code"
        response_message = "Großartig! Bitte geben Sie Ihre Postleitzahl an."

    elif session_data[session_id]['step'] == "zip_code":
        session_data[session_id]['user_details']['zip_code'] = user_message
        session_data[session_id]['step'] = "description"
        response_message = "Fast fertig! Bitte geben Sie eine Beschreibung für das Angebot ein."

    elif session_data[session_id]['step'] == "description":
        session_data[session_id]['user_details']['description'] = user_message
        user_details = session_data[session_id]['user_details']

        # Send the details to Zoho CRM
        zoho_response = send_to_zoho(
            first_name=user_details['first_name'],
            last_name=user_details['last_name'],
            phone=user_details['phone'],
            zip_code=user_details['zip_code'],
            description=user_details['description']
        )

        print(f"Zoho Response: {zoho_response}")
        
        response_message = (f"Danke {user_details['first_name']}! Ihr Angebot wurde übermittelt. "
                            "Möchten Sie noch etwas wissen oder eine andere Frage stellen?")

        # Clear session data, but keep the conversation going
        session_data[session_id]['step'] = None
        session_data[session_id]['user_details'] = {}

    else:
        # Normal conversation if no offer intent
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message,
        )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id, assistant_id=assistant_id_berater
        )

        messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))
        response_message = messages[0].content[0].text.value

    log_chat(thread_id, user_message, response_message)

    response = make_response(jsonify({"response": response_message, "thread_id": thread_id}))
    response.set_cookie('session_id', session_id, httponly=True, samesite='None', secure=True)

    return response


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)
