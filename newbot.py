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
import random  # for random choice
import re

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
    logger.info("OPENAI_ASSISTANT_ID_berater is set")
else:
    logger.error("OPENAI_ASSISTANT_ID_berater is NOT set")

client = OpenAI(api_key=key)
app = Flask(__name__)
# Enable CORS with credentials
CORS(app, supports_credentials=True, origins=["https://probenahmeprotokoll.de", "https://erdbaron.com", "https://ersatzbaustoffverordnung.online", "https://deponieverordnung.online", "https://kreislaufwirtschaftsgesetz.online", "https://laga-pn-98.online", "https://bundesbodenschutzverordnung.online"])

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
            'Geplanter Start': 'geplanter_start',
            'Leistung': 'leistung'
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

        required_fields = [
            'first_name', 'last_name', 'email', 'phone',
            'zip_code', 'quantity', 'description', 'geplanter_start'
        ]
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
        geplanter_start = user_details.get('geplanter_start', '')
        leistung_value = user_details.get('leistung', '')

        # Convert date format if provided
        if geplanter_start:
            try:
                date_obj = datetime.strptime(geplanter_start, '%d.%m.%Y')
                geplanter_start_formatted = date_obj.strftime('%Y-%m-%d')
            except ValueError:
                logger.error(f"Invalid date format for Geplanter Start: {geplanter_start}")
                geplanter_start_formatted = ''
        else:
            geplanter_start_formatted = ''

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
                    "Geplanter_Start": geplanter_start_formatted,
                    "Leistung_Lieferung": leistung_value,
                    "BenutzerIP": user_details.get("ip_address", ""),
                    "Benutzerregion": user_details.get("region", ""),
                    "Benutzerstadt": user_details.get("city", ""),
                    "Gespr_chsverlauf": user_details.get("gespraechsverlauf", "")
                }
            ]
        }

        logger.info(f"Data being sent to Zoho CRM: {data}")
        response = requests.post(zoho_url, json=data, headers=headers)
        logger.info(f"Zoho CRM Response Status Code: {response.status_code}")
        logger.info(f"Zoho CRM Response Text: {response.text}")

        # If unauthorized, try refreshing token and re-sending
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
    """
    Connects to the database using credentials from environment variables.
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
        logger.info("Database connection established.")
        return connection
    except Exception as e:
        logger.error(f"Error connecting to the database: {e}")
        return None


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
            logger.info("Chat data logged to database with IP and location.")
    except Exception as e:
        logger.error(f"Error inserting into the database: {e}")
    finally:
        connection.close()


def log_chat_ersatz(thread_id, user_message, assistant_response, ip_address, region, city):
    """
    Logs the conversation for /ersatzbaustoffverordnung into the ersatzbaustoffverordnung_log table.
    Now stores the user's IP, region, and city (instead of empty strings).
    """
    connection = get_db_connection()
    if connection is None:
        logger.error("Failed to log ersatz chat: No database connection.")
        return
    
    try:
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO ersatzbaustoffverordnung_log 
                (thread_id, user_message, assistant_response, ip_address, region, city)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (thread_id, user_message, assistant_response, ip_address, region, city))
            connection.commit()
            logger.info("Chat data logged to ersatzbaustoffverordnung_log with location fields.")
    except Exception as e:
        logger.error(f"Error inserting into ersatzbaustoffverordnung_log: {e}")
    finally:
        connection.close()


def log_chat_kreislauf(thread_id, user_message, assistant_response):
    """
    Logs chats for /kreislaufwirtschaftsgesetz into kreislaufwirtschaftsgesetz_logs.
    """
    connection = get_db_connection()
    if connection is None:
        logger.error("Failed to log kreislauf chat: No database connection.")
        return
    
    try:
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO kreislaufwirtschaftsgesetz_logs
                (thread_id, user_message, assistant_response, ip_address, region, city)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (thread_id, user_message, assistant_response, '', '', ''))
            connection.commit()
            logger.info("Chat data logged to kreislaufwirtschaftsgesetz_logs.")
    except Exception as e:
        logger.error(f"Error inserting into kreislaufwirtschaftsgesetz_logs: {e}")
    finally:
        connection.close()


def log_chat_bundesbodenschutz(thread_id, user_message, assistant_response):
    """
    Logs chats for /bundesbodenschutzverordnung into bundesbodenschutzverordnung_logs.
    """
    connection = get_db_connection()
    if connection is None:
        logger.error("Failed to log bundesboden chat: No database connection.")
        return
    
    try:
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO bundesbodenschutzverordnung_logs
                (thread_id, user_message, assistant_response, ip_address, region, city)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (thread_id, user_message, assistant_response, '', '', ''))
            connection.commit()
            logger.info("Chat data logged to bundesbodenschutzverordnung_logs.")
    except Exception as e:
        logger.error(f"Error inserting into bundesbodenschutzverordnung_logs: {e}")
    finally:
        connection.close()


def log_chat_lagapn98(thread_id, user_message, assistant_response):
    """
    Logs chats for /lagapn98 into lagapn98_logs.
    """
    connection = get_db_connection()
    if connection is None:
        logger.error("Failed to log lagapn98 chat: No database connection.")
        return
    
    try:
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO lagapn98_logs
                (thread_id, user_message, assistant_response, ip_address, region, city)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (thread_id, user_message, assistant_response, '', '', ''))
            connection.commit()
            logger.info("Chat data logged to lagapn98_logs.")
    except Exception as e:
        logger.error(f"Error inserting into lagapn98_logs: {e}")
    finally:
        connection.close()


def log_chat_deponie(thread_id, user_message, assistant_response):
    """
    Logs chats for /deponieverordnung into deponieverordnung_logs.
    """
    connection = get_db_connection()
    if connection is None:
        logger.error("Failed to log deponie chat: No database connection.")
        return
    
    try:
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO deponieverordnung_logs
                (thread_id, user_message, assistant_response, ip_address, region, city)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (thread_id, user_message, assistant_response, '', '', ''))
            connection.commit()
            logger.info("Chat data logged to deponieverordnung_logs.")
    except Exception as e:
        logger.error(f"Error inserting into deponieverordnung_logs: {e}")
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
        logger.info("Received request at /askberater")

        data = request.json or {}
        user_message = data.get("message", "")
        thread_id_from_body = data.get("threadId")  # Fallback thread ID from front-end
        ip_address = data.get("ip_address", "")
        region = data.get("region", "")
        city = data.get("city", "")

        logger.info(f"User message: {user_message}")
        logger.info(f"Received IP: {ip_address}, Region: {region}, City: {city}")

        # ----------------------------------------------------------------------
        # STEP A: Always retrieve or create the OpenAI thread (and session) FIRST
        session_id = request.cookies.get("session_id")

        # If no session_id, see if front-end gave us a threadId
        if not session_id and thread_id_from_body:
            matching_session_id = None
            for possible_session_id, session_info in session_data.items():
                if session_info["thread"].id == thread_id_from_body:
                    matching_session_id = possible_session_id
                    break
            if matching_session_id:
                logger.info("Found matching session based on front-end threadId.")
                session_id = matching_session_id

        # If still no session_id, create a brand-new one
        if not session_id:
            session_id = str(uuid.uuid4())
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"New session created with ID: {session_id}")
        elif session_id not in session_data:
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"Session data initialized for existing session ID: {session_id}")

        # We now have a valid sessionId, so get the threadId from it
        thread_id = session_data[session_id]["thread"].id
        logger.info(f"Using thread ID: {thread_id}")

        # ----------------------------------------------------------------------
        # STEP B: Define "special" questions + responses
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

        # ----------------------------------------------------------------------
        # STEP C: If user's question is special, we respond from the special list
        if user_message.lower().strip() in SPECIAL_RESPONSES:
            # OPTIONAL: Store the user message in the OpenAI thread if you want context
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=user_message
            )

            # Pick a random response
            random_response = random.choice(SPECIAL_RESPONSES[user_message.lower().strip()])

            # Delay
            time.sleep(1)
            response_message = random_response
            logger.info("Returning a special delayed (random) response.")

            # OPTIONAL: Store the assistant's special response in the thread
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="assistant",
                content=response_message
            )

            # Log to DB
            log_chat("special-no-openai", user_message, response_message, ip_address, region, city)

            # Return this special response AND the same thread_id
            response = make_response(jsonify({"response": response_message, "thread_id": thread_id}))
            response.set_cookie("session_id", session_id, httponly=True, samesite="None", secure=True)
            return response

        # ----------------------------------------------------------------------
        # STEP D: Otherwise, go through normal OpenAI flow

        # Possibly add region info to the user message
        user_message_for_gpt = user_message
        if region and region.lower() != "unavailable":
            user_message_for_gpt = f"(HINWEIS: Der Benutzer befindet sich in {region}.)\n\n{user_message}"

        # 1) Insert user's message (with region hint) into thread
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message_for_gpt
        )

        # 2) Call OpenAI
        run = client.beta.threads.runs.create_and_poll(thread_id=thread_id, assistant_id=assistant_id_berater)
        messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))

        response_message = messages[0].content[0].text.value
        logger.info(f"Response from OpenAI: {response_message}")

        # 3) Check if it's a summary or triggers Zoho, etc.
        if ("zusammenfassung" in response_message.lower()
            or "überblick" in response_message.lower()
            or "summary" in response_message.lower()
            or "zusammenfassen" in response_message.lower()
            or "zusammen" in response_message.lower()):
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
                    # Fetch the entire conversation from the thread
                    all_messages = client.beta.threads.messages.list(thread_id=thread_id)

                    # Build conversation top-to-bottom
                    conversation_history = []
                    for msg in all_messages:
                        # Make sender bold
                        if msg.role == "user":
                            sender = "<strong>User</strong>"
                        else:
                            sender = "<strong>Bot</strong>"

                        # Convert \n to <br> for Rich Text
                        text_html = msg.content[0].text.value.replace("\n", "<br>")
                        conversation_history.append(f"{sender}: {text_html}")

                    # Join each message with <br>
                    full_conversation_html = "<br>".join(conversation_history)

                    # Wrap it in <p> so Zoho displays HTML nicely
                    user_details["gespraechsverlauf"] = f"<p>{full_conversation_html}</p>"

                    # Add IP, region, and city
                    user_details["ip_address"] = ip_address
                    user_details["region"] = region
                    user_details["city"] = city

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

        # 4) Log and return
        log_chat(thread_id, user_message, response_message, ip_address, region, city)

        response = make_response(jsonify({"response": response_message, "thread_id": thread_id}))
        response.set_cookie("session_id", session_id, httponly=True, samesite='None', secure=True)
        return response

    except Exception as e:
        logger.error(f"Error in /askberater: {e}")
        return jsonify({"response": "Entschuldigung, ein Fehler ist aufgetreten."}), 500






@app.route("/ersatzbaustoffverordnung", methods=["POST"])
def ersatzbaustoffverordnung():
    """
    Endpoint for a simple assistant that responds to user questions related to
    Ersatzbaustoffverordnung. Maintains thread IDs for conversation continuity.
    Now also logs IP address, region, and city.
    """
    try:
        logger.info("Received request at /ersatzbaustoffverordnung")

        # Parse the incoming JSON payload
        data = request.json or {}
        user_message = data.get("message", "").strip()
        thread_id_from_body = data.get("threadId", "")  # Optional thread ID from frontend

        ip_address = data.get("ip_address", "Unavailable")
        region = data.get("region", "Unavailable")
        city = data.get("city", "Unavailable")

        logger.info(f"User message: {user_message}, IP: {ip_address}, Region: {region}, City: {city}")

        # Get the assistant ID for this endpoint
        assistant_id = os.getenv("ASSISTANT_ID_ersatzbaustoffverordnung.online")
        if not assistant_id:
            logger.error("ASSISTANT_ID_ersatzbaustoffverordnung is not set in environment variables.")
            return jsonify({"response": "Assistant configuration error."}), 500

        # Session and thread management
        session_id = request.cookies.get("session_id")
        if not session_id and thread_id_from_body:
            matching_session_id = None
            for possible_session_id, session_info in session_data.items():
                if session_info["thread"].id == thread_id_from_body:
                    matching_session_id = possible_session_id
                    break
            if matching_session_id:
                session_id = matching_session_id

        if not session_id:
            session_id = str(uuid.uuid4())
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"New session created with ID: {session_id}")
        elif session_id not in session_data:
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"Session data initialized for existing session ID: {session_id}")

        thread_id = session_data[session_id]["thread"].id
        logger.info(f"Using thread ID: {thread_id}")

        # Add user message to the thread
        client.beta.threads.messages.create(
            thread_id=thread_id, 
            role="user", 
            content=user_message
        )

        # Call the assistant
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id, 
            assistant_id=assistant_id
        )
        messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))

        # Extract the response
        response_message = messages[0].content[0].text.value
        logger.info(f"Response from Ersatzbaustoffverordnung assistant: {response_message}")

        # >>> NOW log the conversation with IP, region, city
        log_chat_ersatz(thread_id, user_message, response_message, ip_address, region, city)

        # Return the assistant's response
        response = make_response(jsonify({"response": response_message, "thread_id": thread_id}))
        response.set_cookie("session_id", session_id, httponly=True, samesite="None", secure=True)
        return response

    except Exception as e:
        logger.error(f"Error in /ersatzbaustoffverordnung: {e}")
        return jsonify({"response": "Entschuldigung, ein Fehler ist aufgetreten."}), 500



@app.route("/kreislaufwirtschaftsgesetz", methods=["POST"])
def kreislaufwirtschaftsgesetz():
    """
    Endpoint for a simple assistant about Kreislaufwirtschaftsgesetz.
    Logs to kreislaufwirtschaftsgesetz_logs.
    """
    try:
        logger.info("Received request at /kreislaufwirtschaftsgesetz")

        data = request.json or {}
        user_message = data.get("message", "").strip()
        thread_id_from_body = data.get("threadId")  # Optional

        assistant_id = os.getenv("ASSISTANT_ID_kreislaufwirtschaftsgesetz.online")
        if not assistant_id:
            logger.error("ASSISTANT_ID_kreislaufwirtschaftsgesetz is not set.")
            return jsonify({"response": "Assistant configuration error."}), 500

        # Session logic
        session_id = request.cookies.get("session_id")
        if not session_id and thread_id_from_body:
            matching_session_id = None
            for possible_session_id, session_info in session_data.items():
                if session_info["thread"].id == thread_id_from_body:
                    matching_session_id = possible_session_id
                    break
            if matching_session_id:
                session_id = matching_session_id

        if not session_id:
            session_id = str(uuid.uuid4())
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"New session created with ID: {session_id}")
        elif session_id not in session_data:
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"Session data initialized for existing session ID: {session_id}")

        thread_id = session_data[session_id]["thread"].id
        logger.info(f"Using thread ID: {thread_id}")

        # Send user message
        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)

        # Call the assistant
        run = client.beta.threads.runs.create_and_poll(thread_id=thread_id, assistant_id=assistant_id)
        messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))

        response_message = messages[0].content[0].text.value
        logger.info(f"Response from Kreislaufwirtschaftsgesetz: {response_message}")

        # Log to kreislauf table
        log_chat_kreislauf(thread_id, user_message, response_message)

        response = make_response(jsonify({"response": response_message, "thread_id": thread_id}))
        response.set_cookie("session_id", session_id, httponly=True, samesite="None", secure=True)
        return response

    except Exception as e:
        logger.error(f"Error in /kreislaufwirtschaftsgesetz: {e}")
        return jsonify({"response": "Entschuldigung, ein Fehler ist aufgetreten."}), 500


@app.route("/bundesbodenschutzverordnung", methods=["POST"])
def bundesbodenschutzverordnung():
    """
    Endpoint for a simple assistant about Bundesbodenschutzverordnung.
    Logs to bundesbodenschutzverordnung_logs.
    """
    try:
        logger.info("Received request at /bundesbodenschutzverordnung")

        data = request.json or {}
        user_message = data.get("message", "").strip()
        thread_id_from_body = data.get("threadId", "")

        assistant_id = os.getenv("ASSISTANT_ID_bundesbodenschutzverordnung.online")
        if not assistant_id:
            logger.error("ASSISTANT_ID_bundesbodenschutzverordnung is not set.")
            return jsonify({"response": "Assistant configuration error."}), 500

        # Session logic
        session_id = request.cookies.get("session_id")
        if not session_id and thread_id_from_body:
            matching_session_id = None
            for possible_session_id, session_info in session_data.items():
                if session_info["thread"].id == thread_id_from_body:
                    matching_session_id = possible_session_id
                    break
            if matching_session_id:
                session_id = matching_session_id

        if not session_id:
            session_id = str(uuid.uuid4())
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"New session created with ID: {session_id}")
        elif session_id not in session_data:
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"Session data initialized for existing session ID: {session_id}")

        thread_id = session_data[session_id]["thread"].id
        logger.info(f"Using thread ID: {thread_id}")

        # Send user message
        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)

        # Call assistant
        run = client.beta.threads.runs.create_and_poll(thread_id=thread_id, assistant_id=assistant_id)
        messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))

        response_message = messages[0].content[0].text.value
        logger.info(f"Response from Bundesbodenschutzverordnung: {response_message}")

        # Log to bundesbodenschutzverordnung_logs
        log_chat_bundesbodenschutz(thread_id, user_message, response_message)

        response = make_response(jsonify({"response": response_message, "thread_id": thread_id}))
        response.set_cookie("session_id", session_id, httponly=True, samesite="None", secure=True)
        return response

    except Exception as e:
        logger.error(f"Error in /bundesbodenschutzverordnung: {e}")
        return jsonify({"response": "Entschuldigung, ein Fehler ist aufgetreten."}), 500


@app.route("/lagapn98", methods=["POST"])
def lagapn98():
    """
    Endpoint for a simple assistant about LAGA PN 98.
    Logs to lagapn98_logs.
    """
    try:
        logger.info("Received request at /lagapn98")

        data = request.json or {}
        user_message = data.get("message", "").strip()
        thread_id_from_body = data.get("threadId", "")

        assistant_id = os.getenv("ASSISTANT_ID_laga-pn-98.online")
        if not assistant_id:
            logger.error("ASSISTANT_ID_lagapn98 is not set.")
            return jsonify({"response": "Assistant configuration error."}), 500

        session_id = request.cookies.get("session_id")
        if not session_id and thread_id_from_body:
            matching_session_id = None
            for possible_session_id, session_info in session_data.items():
                if session_info["thread"].id == thread_id_from_body:
                    matching_session_id = possible_session_id
                    break
            if matching_session_id:
                session_id = matching_session_id

        if not session_id:
            session_id = str(uuid.uuid4())
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"New session created with ID: {session_id}")
        elif session_id not in session_data:
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"Session data initialized for existing session ID: {session_id}")

        thread_id = session_data[session_id]["thread"].id
        logger.info(f"Using thread ID: {thread_id}")

        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)

        run = client.beta.threads.runs.create_and_poll(thread_id=thread_id, assistant_id=assistant_id)
        messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))

        response_message = messages[0].content[0].text.value
        logger.info(f"Response from LAGA PN 98: {response_message}")

        # Log to lagapn98_logs
        log_chat_lagapn98(thread_id, user_message, response_message)

        response = make_response(jsonify({"response": response_message, "thread_id": thread_id}))
        response.set_cookie("session_id", session_id, httponly=True, samesite="None", secure=True)
        return response

    except Exception as e:
        logger.error(f"Error in /lagapn98: {e}")
        return jsonify({"response": "Entschuldigung, ein Fehler ist aufgetreten."}), 500


@app.route("/deponieverordnung", methods=["POST"])
def deponieverordnung():
    """
    Endpoint for a simple assistant about Deponieverordnung.
    Logs to deponieverordnung_logs.
    """
    try:
        logger.info("Received request at /deponieverordnung")

        data = request.json or {}
        user_message = data.get("message", "").strip()
        thread_id_from_body = data.get("threadId", "")

        assistant_id = os.getenv("ASSISTANT_ID_deponieverordnung.online")
        if not assistant_id:
            logger.error("ASSISTANT_ID_deponieverordnung is not set.")
            return jsonify({"response": "Assistant configuration error."}), 500

        session_id = request.cookies.get("session_id")
        if not session_id and thread_id_from_body:
            matching_session_id = None
            for possible_session_id, session_info in session_data.items():
                if session_info["thread"].id == thread_id_from_body:
                    matching_session_id = possible_session_id
                    break
            if matching_session_id:
                session_id = matching_session_id

        if not session_id:
            session_id = str(uuid.uuid4())
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"New session created with ID: {session_id}")
        elif session_id not in session_data:
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"Session data initialized for existing session ID: {session_id}")

        thread_id = session_data[session_id]["thread"].id
        logger.info(f"Using thread ID: {thread_id}")

        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)

        run = client.beta.threads.runs.create_and_poll(thread_id=thread_id, assistant_id=assistant_id)
        messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))

        response_message = messages[0].content[0].text.value
        logger.info(f"Response from Deponieverordnung: {response_message}")

        # Log to deponieverordnung_logs
        log_chat_deponie(thread_id, user_message, response_message)

        response = make_response(jsonify({"response": response_message, "thread_id": thread_id}))
        response.set_cookie("session_id", session_id, httponly=True, samesite="None", secure=True)
        return response

    except Exception as e:
        logger.error(f"Error in /deponieverordnung: {e}")
        return jsonify({"response": "Entschuldigung, ein Fehler ist aufgetreten."}), 500



@app.route("/pricefinder", methods=["POST"])
def pricefinder():
    """
    Replaces the old /pricefinder endpoint that used Zoho CRM.
    1) Calls the assistant to get a numeric price.
    2) Stores that price in 'preisanfragen' table (SQL).
    3) Returns the price to the caller.
    """
    try:
        logger.info("Received request at /pricefinder")

        data = request.json or {}
        postcode   = data.get("postcode", "").strip()
        verordnung = data.get("verordnung", "").strip()
        klasse     = data.get("klasse", "").strip()

        # Session logic remains if you want to keep thread IDs and conversation tracking
        thread_id_from_body = data.get("threadId", "")
        session_id = request.cookies.get("session_id")

        # Provide a default or random session if none exists
        if not session_id and thread_id_from_body:
            matching_session_id = None
            for possible_session_id, session_info in session_data.items():
                if session_info["thread"].id == thread_id_from_body:
                    matching_session_id = possible_session_id
                    break
            if matching_session_id:
                session_id = matching_session_id

        if not session_id:
            session_id = str(uuid.uuid4())
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"New session created with ID: {session_id}")
        elif session_id not in session_data:
            session_data[session_id] = {
                "thread": client.beta.threads.create(),
                "user_details": {},
                "summary": None
            }
            logger.info(f"Session data re-initialized for existing session ID: {session_id}")

        thread_id = session_data[session_id]["thread"].id
        logger.info(f"Using thread ID: {thread_id}")

        # Step 1) Create a user message for the assistant
        user_message = (
            f"Postcode: {postcode}, Verordnung: {verordnung}, Klasse: {klasse}. "
            f"Please return only the numeric price in euros (no extra text)."
        )

        # Send the user message to OpenAI
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message
        )

        # Step 2) Run the assistant
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=os.getenv("ASSISTANT_ID_pricefinder", "")
        )
        messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))

        if not messages:
            logger.error("No messages returned from pricefinder assistant.")
            return jsonify({"response": "Keine Antwort erhalten.", "thread_id": thread_id}), 200

        response_message = messages[0].content[0].text.value
        logger.info(f"Response from pricefinder assistant: {response_message}")

        # Step 3) Parse numeric price
        price_str = re.sub(r'[^0-9.,]', '', response_message.strip())
        price_str = price_str.replace(',', '.')
        try:
            numeric_price = float(price_str)
            logger.info(f"Parsed numeric price => {numeric_price}")
        except ValueError:
            logger.error(f"Could not parse numeric price from => {price_str}")
            numeric_price = None

        # Step 4) If numeric, store in SQL 'preisanfragen'
        if numeric_price is not None:
            store_in_preisanfragen(postcode, verordnung, klasse, numeric_price)
        else:
            logger.info("Assistant did not return a numeric price => skip SQL insert.")

        # Return JSON
        response = make_response(jsonify({
            "response": response_message,  # show exact assistant text
            "thread_id": thread_id
        }))
        response.set_cookie("session_id", session_id, httponly=True, samesite="None", secure=True)
        return response

    except Exception as e:
        logger.error(f"Error in /pricefinder: {e}")
        return jsonify({"response": "Entschuldigung, ein Fehler ist aufgetreten."}), 500


def store_in_preisanfragen(postcode, verordnung, klasse, price):
    """
    Store the assistant-fetched price in the 'preisanfragen' table in MySQL.
    The table has columns: id, postcode, verordnung, klasse, preis, created_at
    'id' and 'created_at' are auto-managed. We'll insert the rest.
    """
    connection = get_db_connection()
    if connection is None:
        logger.error("Failed to store in preisanfragen: No DB connection.")
        return

    try:
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO preisanfragen (postcode, verordnung, klasse, preis)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(sql, (postcode, verordnung, klasse, price))
            connection.commit()
            logger.info("Inserted into preisanfragen with price => %s", price)
    except Exception as e:
        logger.error(f"Error inserting into preisanfragen: {e}")
    finally:
        connection.close()

## 2) **New `/preisvorschlag` Endpoint** (Replace Entirely)

@app.route("/preisvorschlag", methods=["POST"])
def preisvorschlag():
    """
    Receives the user's suggested price + the system's fetched price,
    along with postcode, verordnung, klasse.
    Stores into 'preisvorschlag' table in MySQL:
      - id (auto)
      - postcode
      - verordnung
      - klasse
      - suggested_price
      - preis (the system's fetched price)
      - created_at (auto)
    Returns JSON { "message": "Preisvorschlag gespeichert!" } on success.
    """
    try:
        logger.info("Received request at /preisvorschlag")

        data = request.json or {}
        fetched_price   = data.get("fetchedPrice", "").strip()
        suggested_price = data.get("suggestedPrice", "").strip()
        postcode        = data.get("postcode", "").strip()
        verordnung      = data.get("verordnung", "").strip()
        klasse          = data.get("klasse", "").strip()

        # Convert 'fetched_price' and 'suggested_price' to decimal with '.' if needed
        # Remove euro symbols or commas
        fetched_float   = parse_price_to_float(fetched_price)
        suggested_float = parse_price_to_float(suggested_price)

        # Store in MySQL
        store_in_preisvorschlag(postcode, verordnung, klasse, fetched_float, suggested_float)

        return jsonify({"message": "Preisvorschlag gespeichert!"})

    except Exception as e:
        logger.error(f"Error in /preisvorschlag: {e}")
        return jsonify({"message": "Ein Fehler ist aufgetreten."}), 500


def parse_price_to_float(price_str):
    """
    Utility: Convert a user price like '15,50', '15.50€' into float (e.g. 15.5).
    If it fails, returns 0.0 or any default.
    """
    tmp = re.sub(r'[^0-9.,]', '', price_str)
    tmp = tmp.replace(',', '.')
    try:
        return float(tmp)
    except:
        return 0.0


def store_in_preisvorschlag(postcode, verordnung, klasse, fetched_price, suggested_price):
    """
    Insert the user-suggested price into the 'preisvorschlag' table.
    Table columns: id, postcode, verordnung, klasse, suggested_price, preis, created_at
    'id' and 'created_at' are auto, so we insert the rest.
    """
    connection = get_db_connection()
    if connection is None:
        logger.error("No DB connection => can't store preisvorschlag.")
        return

    try:
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO preisvorschlag (postcode, verordnung, klasse, suggested_price, preis)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (postcode, verordnung, klasse, suggested_price, fetched_price))
            connection.commit()
            logger.info("Inserted into preisvorschlag => suggested=%s, fetched=%s", suggested_price, fetched_price)
    except Exception as e:
        logger.error(f"Error inserting into preisvorschlag: {e}")
    finally:
        connection.close()




if __name__ == "__main__":
    # Run the Flask app
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)
