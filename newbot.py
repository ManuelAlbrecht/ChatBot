from flask import Flask, request, jsonify, render_template, make_response
from flask_cors import CORS
import os
from openai import OpenAI
from dotenv import load_dotenv
import pymysql
import uuid
import requests
import time
import logging
from datetime import datetime

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

key = os.getenv("OPENAI_API_KEY")
assistant_id_berater = os.getenv("ASSISTANT_ID_berater")

# Log environment variables
logger.info("Checking environment variables...")
if key:
    logger.info("OPENAI_API_KEY is set")
else:
    logger.error("OPENAI_API_KEY is NOT set")

if assistant_id_berater:
    logger.info("ASSISTANT_ID_berater is set")
else:
    logger.error("ASSISTANT_ID_berater is NOT set")

client = OpenAI(api_key=key)
app = Flask(__name__)
# Enable CORS with credentials
CORS(app, supports_credentials=True, origins=["https://probenahmeprotokoll.de", "https://erdbaron.com"])

# Dictionary to store session data (thread IDs and user details)
session_data = {}

# Variables to manage tokens for Zoho API
access_token = os.getenv("ZOHO_ACCESS_TOKEN")
refresh_token = os.getenv("ZOHO_REFRESH_TOKEN")
client_id = os.getenv("ZOHO_CLIENT_ID")
client_secret = os.getenv("ZOHO_CLIENT_SECRET")
token_expires_in = 3600  # Time in seconds
token_last_refresh_time = time.time()

# Log Zoho credentials
logger.info("Checking Zoho API credentials...")
if access_token:
    logger.info("ZOHO_ACCESS_TOKEN is set")
else:
    logger.error("ZOHO_ACCESS_TOKEN is NOT set")

if refresh_token:
    logger.info("ZOHO_REFRESH_TOKEN is set")
else:
    logger.error("ZOHO_REFRESH_TOKEN is NOT set")

if client_id:
    logger.info("ZOHO_CLIENT_ID is set")
else:
    logger.error("ZOHO_CLIENT_ID is NOT set")

if client_secret:
    logger.info("ZOHO_CLIENT_SECRET is set")
else:
    logger.error("ZOHO_CLIENT_SECRET is NOT set")


def refresh_access_token():
    global access_token, token_last_refresh_time, token_expires_in
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
        token_expires_in = response_data.get('expires_in', 3600)
        token_last_refresh_time = time.time()
        logger.info("Access token refreshed.")
    else:
        logger.error(f"Failed to refresh access token: {response.text}")
        raise Exception("Failed to refresh access token")


def ensure_valid_access_token():
    global token_last_refresh_time, token_expires_in
    current_time = time.time()
    if current_time - token_last_refresh_time >= token_expires_in:
        refresh_access_token()


def extract_details_from_summary(summary):
    try:
        logger.info(f"Extracting details from summary:\n{summary}")
        details = {}
        field_mapping = {
            'Anrede': 'salutation',
            'Vorname': 'first_name',
            'Nachname': 'last_name',
            'Email': 'email',
            'Telefon': 'phone',
            'Postleitzahl': 'zip_code',
            'Menge': 'quantity',
            'Beschreibung': 'description',
            'Betreff': 'subject',
            'Geplanter Start': 'geplanter_start'
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
                    logger.info(f"Extracted {key}: {value}")
                else:
                    logger.warning(f"Ignored unrecognized field: {field_name}")
            else:
                logger.warning(f"Ignored line without colon: {line}")

        required_fields = ['first_name', 'last_name', 'email', 'phone', 'zip_code', 'quantity', 'description', 'geplanter_start']
        if all(field in details for field in required_fields):
            logger.info(f"Parsed Details: {details}")
            return details
        else:
            missing_fields = [field for field in required_fields if field not in details]
            logger.error(f"Missing fields: {missing_fields}")
            return None
    except Exception as e:
        logger.error(f"Error extracting details from summary: {e}")
        return None


def send_to_zoho(user_details):
    try:
        ensure_valid_access_token()
        zoho_url = "https://www.zohoapis.eu/crm/v3/Deals"
        headers = {
            'Authorization': f'Zoho-oauthtoken {access_token}',
            'Content-Type': 'application/json',
        }

        first_name = user_details.get('first_name', '')
        last_name = user_details.get('last_name', '')
        phone = user_details.get('phone', '')
        zip_code = user_details.get('zip_code', '')
        description = user_details.get('description', '')
        email = user_details.get('email', '')
        quantity = user_details.get('quantity', '')
        subject = user_details.get('subject', '')
        geplannter_start = user_details.get('geplanter_start', '')

        if geplannter_start:
            try:
                date_obj = datetime.strptime(geplannter_start, '%d.%m.%Y')
                geplannter_start_formatted = date_obj.strftime('%Y-%m-%d')
            except ValueError:
                logger.error(f"Invalid date format for Geplanter Start: {geplannter_start}")
                geplannter_start_formatted = ''
        else:
            geplannter_start_formatted = ''

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
                    "Gesch_tzte_Menge_m": quantity,
                    "Betreff": subject,
                    "Pipeline": pipeline_value,
                    "Stage": stage_value,
                    "Lead_Source": "Chatbot",
                    "Geplanter_Start": geplannter_start_formatted
                }
            ]
        }

        logger.info(f"Data being sent to Zoho CRM: {data}")
        response = requests.post(zoho_url, json=data, headers=headers)
        logger.info(f"Zoho CRM Response Status Code: {response.status_code}")
        logger.info(f"Zoho CRM Response Text: {response.text}")

        if response.status_code == 401:
            logger.warning("Unauthorized. Refreshing access token and retrying...")
            refresh_access_token()
            headers['Authorization'] = f'Zoho-oauthtoken {access_token}'
            response = requests.post(zoho_url, json=data, headers=headers)
            logger.info(f"Retry Zoho CRM Response Status Code: {response.status_code}")
            logger.info(f"Retry Zoho CRM Response Text: {response.text}")

        if response.status_code in [200, 201]:
            logger.info("Data successfully sent to Zoho CRM.")
            logger.info(f"Response: {response.json()}")
        else:
            logger.error(f"Failed to send data to Zoho CRM. Status: {response.status_code}")
            logger.error(f"Response: {response.text}")

    except Exception as e:
        logger.error(f"Error while sending to Zoho: {e}")


def get_db_connection():
    try:
        connection = pymysql.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASS'),
            database=os.getenv('DB_NAME'),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        logger.info("Database connection established.")
        return connection
    except Exception as e:
        logger.error(f"Error connecting to the database: {e}")
        return None


def log_chat(thread_id, user_message, assistant_response, ip_address=None, region=None, city=None):
    connection = get_db_connection()
    if connection is None:
        logger.error("Failed to log chat: No database connection.")
        return
    try:
        with connection.cursor() as cursor:
            sql = """
            INSERT INTO chatlog (thread_id, user_message, assistant_response, ip_address, region, city) 
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (thread_id, user_message, assistant_response, ip_address, region, city))
            connection.commit()
            logger.info("Chat data logged to database with IP and location.")
    except Exception as e:
        logger.error(f"Error inserting into the database: {e}")
    finally:
        connection.close()


@app.route("/askberater", methods=["POST"])
def ask1():
    try:
        logger.info("Received request at /askberater")
        user_message = request.json.get("message", "")
        ip_address = request.json.get("ip_address", "")
        region = request.json.get("region", "")
        city = request.json.get("city", "")

        logger.info(f"User message: {user_message}")
        user_message_lower = user_message.lower()
        session_id = request.cookies.get('session_id')

        if not session_id:
            session_id = str(uuid.uuid4())
            session_data[session_id] = {
                'thread': client.beta.threads.create(),
                'user_details': {},
                'summary': None
            }
            logger.info(f"New session created with ID: {session_id}")
        elif session_id not in session_data:
            session_data[session_id] = {
                'thread': client.beta.threads.create(),
                'user_details': {},
                'summary': None
            }
            logger.info(f"Session data initialized for existing session ID: {session_id}")

        thread_id = session_data[session_id]['thread'].id
        logger.info(f"Using thread ID: {thread_id}")

        # Send the user's message to the assistant
        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)
        run = client.beta.threads.runs.create_and_poll(thread_id=thread_id, assistant_id=assistant_id_berater)
        messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))
        response_message = messages[0].content[0].text.value
        logger.info(f"Response from OpenAI: {response_message}")

        if ("zusammenfassung" in response_message.lower() or
            "überblick" in response_message.lower() or
            "summary" in response_message.lower() or
            "zusammenfassen" in response_message.lower() or
            "zusammen" in response_message.lower()):
            session_data[session_id]['summary'] = response_message
            logger.info(f"Summary stored for session {session_id}.")

        confirmation_response_phrases = [
            "prima! dann werde ich die anfrage so an meine kollegen weiterleiten.",
            "prima! ich werde die anfrage so an meine kollegen weiterleiten.",
            "ihre anfrage wird weitergeleitet.",
            "prima! dann leite ich die anfrage an meine kollegen weiter.",
            "super! ich werde die anfrage an meine kollegen weiterleiten."
        ]

        if any(phrase in response_message.lower() for phrase in confirmation_response_phrases):
            logger.info("Assistant provided the confirmation message.")
            confirmed_summary = session_data[session_id].get('summary')
            if confirmed_summary:
                user_details = extract_details_from_summary(confirmed_summary)
                if user_details:
                    session_data[session_id]['user_details'] = user_details
                    logger.info(f"Parsed User Details: {user_details}")
                    send_to_zoho(user_details)
                    response_message += "\n\nIhre Daten wurden erfolgreich übermittelt."
                else:
                    logger.error("Failed to parse user details from the summary.")
                    response_message = "Entschuldigung, es gab ein Problem beim Verarbeiten Ihrer Daten."
            else:
                logger.error("No summary found to confirm.")
                response_message = "Entschuldigung, ich konnte Ihre Zusammenfassung nicht finden."
        else:
            logger.info("Assistant did not provide the confirmation message.")

        # Log chat with IP and location
        log_chat(thread_id, user_message, response_message, ip_address, region, city)

        response = make_response(jsonify({"response": response_message, "thread_id": thread_id}))
        response.set_cookie('session_id', session_id, httponly=True, samesite='None', secure=True)
        return response
    except Exception as e:
        logger.error(f"Error in /askberater: {e}")
        return jsonify({"response": "Entschuldigung, ein Fehler ist aufgetreten."}), 500


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)
