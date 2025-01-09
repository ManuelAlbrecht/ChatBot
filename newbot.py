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
import random


load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Enable CORS with credentials
CORS(app, supports_credentials=True, origins=["https://probenahmeprotokoll.de", "https://erdbaron.com"])

# --- Global Variables and Setup ---
key = os.getenv("OPENAI_API_KEY")
assistant_id_berater = os.getenv("ASSISTANT_ID_berater")

access_token = os.getenv("ZOHO_ACCESS_TOKEN")
refresh_token = os.getenv("ZOHO_REFRESH_TOKEN")
client_id = os.getenv("ZOHO_CLIENT_ID")
client_secret = os.getenv("ZOHO_CLIENT_SECRET")
token_expires_in = 3600  # Time in seconds
token_last_refresh_time = time.time()

client = OpenAI(api_key=key)

# In-memory session data
session_data = {}

# Optional: Use requests.Session to reuse TCP connections for Zoho
zoho_session = requests.Session()



def get_db_connection():
    """
    Connects to the database using credentials from environment variables.
    If you want to use pooling, comment out below code and uncomment pool usage.
    """
    try:
        connection = pymysql.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASS'),
            database=os.getenv('DB_NAME'),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return connection
    except Exception as e:
        logger.error(f"Error connecting to the database: {e}")
        return None


def log_startup_info():
    """
    Check environment variables once on startup, log them if needed.
    """
    # Log environment variables
    logger.info("Checking environment variables on startup...")
    if key:
        logger.info("OPENAI_API_KEY is set")
    else:
        logger.error("OPENAI_API_KEY is NOT set")

    if assistant_id_berater:
        logger.info("OPENAI_ASSISTANT_ID_berater is set")
    else:
        logger.error("OPENAI_ASSISTANT_ID_berater is NOT set")

    # Log Zoho credentials
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
    """
    Refreshes the Zoho CRM access token using the provided refresh token.
    """
    global access_token, token_last_refresh_time, token_expires_in
    url = "https://accounts.zoho.eu/oauth/v2/token"
    payload = {
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'refresh_token'
    }
    # Use zoho_session to keep connections alive
    response = zoho_session.post(url, params=payload)
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
    """
    Ensures the Zoho CRM access token is still valid; if not, refresh it.
    """
    global token_last_refresh_time, token_expires_in
    current_time = time.time()
    if current_time - token_last_refresh_time >= token_expires_in:
        refresh_access_token()


def extract_details_from_summary(summary):
    """
    Takes an assistant-generated summary and extracts user details (like name, email, phone, etc.).
    Returns a dictionary of details if successful, else None.
    """
    try:
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
            # If there's no colon, ignore the line silently.

        required_fields = [
            'first_name', 'last_name', 'email', 'phone',
            'zip_code', 'quantity', 'description', 'geplanter_start'
        ]
        if all(field in details for field in required_fields):
            return details
        else:
            missing_fields = [field for field in required_fields if field not in details]
            logger.error(f"Missing fields in summary: {missing_fields}")
            return None
    except Exception as e:
        logger.error(f"Error extracting details from summary: {e}")
        return None


def send_to_zoho(user_details):
    """
    Sends the extracted user details to Zoho CRM as a new Deal.
    """
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

        # Convert date format if provided
        if geplannter_start:
            try:
                date_obj = datetime.strptime(geplanter_start, '%d.%m.%Y')
                geplannter_start_formatted = date_obj.strftime('%Y-%m-%d')
            except ValueError:
                logger.error(f"Invalid date format for Geplanter Start: {geplanter_start}")
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

        response = zoho_session.post(zoho_url, json=data, headers=headers)
        if response.status_code == 401:
            logger.warning("Unauthorized. Refreshing access token and retrying...")
            refresh_access_token()
            headers['Authorization'] = f'Zoho-oauthtoken {access_token}'
            response = zoho_session.post(zoho_url, json=data, headers=headers)

        if response.status_code in [200, 201]:
            logger.info("Data successfully sent to Zoho CRM.")
        else:
            logger.error(f"Failed to send data to Zoho CRM. Status: {response.status_code}")
            logger.error(f"Response: {response.text}")

    except Exception as e:
        logger.error(f"Error while sending to Zoho: {e}")


def log_chat(thread_id, user_message, assistant_response, ip_address=None, region=None, city=None):
    """
    Logs the conversation (user_message and assistant_response) into the database, if connected.
    """
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
    except Exception as e:
        logger.error(f"Error inserting into the database: {e}")
    finally:
        connection.close()


@app.route("/askberater", methods=["POST"])
def ask1():
    """
    Main endpoint for handling user queries to the chatbot/assistant.
    Checks if the query matches a "special question" that requires a delay
    and a random response. Otherwise, it falls back to the normal OpenAI logic.
    Either way, we give the user the same threadId.
    """
    try:
        data = request.get_json(silent=True) or {}
        user_message = data.get("message", "")
        thread_id_from_body = data.get("threadId")
        ip_address = data.get("ip_address", "")
        region = data.get("region", "")
        city = data.get("city", "")

        user_message_lower = user_message.lower().strip()

        session_id = request.cookies.get("session_id")

        # Attempt to match an existing session if no cookie but a threadId was provided
        if not session_id and thread_id_from_body:
            for possible_session_id, session_info in session_data.items():
                if session_info["thread"].id == thread_id_from_body:
                    session_id = possible_session_id
                    break

        # Create a brand-new session if necessary
        if not session_id:
            session_id = str(uuid.uuid4())
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
        elif session_id not in session_data:
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }

        # Retrieve the thread ID
        thread_id = session_data[session_id]["thread"].id

        SPECIAL_RESPONSES = {
            "ich benötige ein baugrundgutachten": [
                "Hallo! Gerne helfe ich Ihnen dabei. Wissen Sie, wie viele Rammkernsondierungen Sie benötigen oder haben Sie genaue Vorgaben für das Baugrundgutachten, oder benötigen Sie Beratung?",
                "Guten Tag! Benötigen Sie allgemeine Infos zum Baugrundgutachten oder möchten Sie direkt einen Preis?",
                "Guten Tag! Möchten Sie einen Preis wissen oder haben Sie andere Fragen?"
            ],
            "ich benötige eine deklarationsanalyse": [
                "Super! Zwei Fragen hierzu: 1. Wissen Sie, nach welcher Verordnung die Deklarationsanalyse durchgeführt werden soll? 2. Wie viele Laboranalysen benötigen Sie? Wenn nicht, können wir das zusammen klären.",
                "Kein Problem! Wissen Sie, nach welcher Verordnung die Deklarationsanalyse durchgeführt werden soll und wie viele Laboranalysen Sie benötigen? Wenn nicht, können wir das zusammen klären.",
                "Okay! Und wissen Sie schon was für eine Deklarationsanalyse Sie benötigen, also nach welcher Verordnung oder sollen wir das zusammen klären?"
            ],
            "ich möchte boden / bauschutt entsorgen": [
                "Gerne! Haben Sie schon eine Deklarationsanalyse für das Material vorliegen?",
                "Okay! Haben Sie bereits eine Deklarationsanalyse für das Material? Falls ja, können Sie hier auf der Webseite eine Anfrage stellen und die Deklarationsanalyse samt Probenahmeprotokoll direkt hochladen, damit wir Ihnen ein Preis nennen können.",
                "Kein Problem! Haben Sie bereits eine Deklarationsanalyse für das Material vorliegen? Falls ja, können Sie diese hochladen oder die relevanten Informationen teilen. Falls keine Analyse vorliegt, könnte ich Ihnen die Kosten für eine Deklarationsanalyse berechnen. Wie möchten Sie fortfahren?"
            ],
            "ich benötige boden / recyclingmaterial": [
                "Hallo! Wie viel Material benötigen Sie denn?",
                "Okay! Brauchen Sie Boden oder Recyclingmaterial?",
                "Gerne! Wie viel und was für Material benötigen Sie denn?"
            ]
        }

        # Handle "special" response
        if user_message_lower in SPECIAL_RESPONSES:
            # Log user message to the thread (optionally, to keep context)
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=user_message
            )

            # Pick a random response
            random_response = random.choice(SPECIAL_RESPONSES[user_message_lower])
            # Delay
            time.sleep(1)  # keep the functionality as is

            response_message = random_response

            # Log assistant's special response to the thread (optionally)
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="assistant",
                content=response_message
            )

            # Log to DB
            log_chat("special-no-openai", user_message, response_message, ip_address, region, city)

            # Return the special response
            response = make_response(jsonify({"response": response_message, "thread_id": thread_id}))
            response.set_cookie("session_id", session_id, httponly=True, samesite="None", secure=True)
            return response

        # Otherwise, normal OpenAI flow
        # 1) Insert user message
        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)

        # 2) Call OpenAI
        run = client.beta.threads.runs.create_and_poll(thread_id=thread_id, assistant_id=assistant_id_berater)
        messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))
        response_message = messages[0].content[0].text.value

        # 3) If message is a summary or includes “zusammenfassung” etc., store it
        if any(word in response_message.lower()
               for word in ["zusammenfassung", "überblick", "summary", "zusammenfassen", "zusammen "]):
            session_data[session_id]['summary'] = response_message

        # 4) If the response includes a known "confirmation" phrase, attempt to parse summary and send to Zoho
        confirmation_response_phrases = [
            "prima! dann werde ich die anfrage so an meine kollegen weiterleiten.",
            "prima! ich werde die anfrage so an meine kollegen weiterleiten.",
            "ihre anfrage wird weitergeleitet.",
            "prima! dann leite ich die anfrage an meine kollegen weiter.",
            "super! ich werde die anfrage an meine kollegen weiterleiten."
        ]
        if any(phrase in response_message.lower() for phrase in confirmation_response_phrases):
            confirmed_summary = session_data[session_id].get('summary')
            if confirmed_summary:
                user_details = extract_details_from_summary(confirmed_summary)
                if user_details:
                    session_data[session_id]['user_details'] = user_details
                    send_to_zoho(user_details)
                    response_message += "\n\nIhre Daten wurden erfolgreich übermittelt."
                else:
                    logger.error("Failed to parse user details from the summary.")
                    response_message = "Entschuldigung, es gab ein Problem beim Verarbeiten Ihrer Daten."
            else:
                logger.error("No summary found to confirm.")
                response_message = "Entschuldigung, ich konnte Ihre Zusammenfassung nicht finden."

        # 5) Log chat to DB and return
        log_chat(thread_id, user_message, response_message, ip_address, region, city)
        response = make_response(jsonify({"response": response_message, "thread_id": thread_id}))
        response.set_cookie("session_id", session_id, httponly=True, samesite='None', secure=True)
        return response

    except Exception as e:
        logger.error(f"Error in /askberater: {e}")
        return jsonify({"response": "Entschuldigung, ein Fehler ist aufgetreten."}), 500


if __name__ == "__main__":
    # Log environment variable info once
    log_startup_info()
    # Run the Flask app
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)
