from flask import Flask, request, jsonify, render_template, make_response
from flask_cors import CORS
import os
from openai import OpenAI
from dotenv import load_dotenv
import pymysql
import uuid

load_dotenv()

key = os.getenv("OPENAI_API_KEY")
assistant_id_berater = os.getenv("ASSISTANT_ID_berater")

client = OpenAI(api_key=key)
app = Flask(__name__)
CORS(app)

# Dictionary to store session data (e.g., thread IDs)
session_data = {}

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

# Serve the index1.html from templates folder for the /askberater route
@app.route("/verkaufsberater", methods=["GET"])
def serve_frontend():
    return render_template("index1.html")  # Flask will look for this in the 'templates' folder

# Handle the chat functionality for POST requests
# Handle the chat functionality for POST requests
@app.route("/verkaufsberater", methods=["POST"])
def ask1():
    user_message = request.json.get("message")
    
    # Get or create the session ID and associate it with a thread
    session_id = request.cookies.get('session_id')
    
    if not session_id:  # If no session ID found, create one
        session_id = str(uuid.uuid4())
        session_data[session_id] = client.beta.threads.create()

    if session_id not in session_data:
        session_data[session_id] = client.beta.threads.create()
    
    # Use the thread ID associated with this session
    thread_id = session_data[session_id].id

    # Create a message in the session's thread
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message,
    )

    # Generate a response
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread_id, assistant_id=assistant_id_berater
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))
    message_content = messages[0].content[0].text.value  # Extract the plain text value

    # Log the chat (thread_id, user message, assistant response)
    log_chat(thread_id, user_message, message_content)

    # Prepare response with the session ID stored in a cookie
    response = make_response(jsonify({"response": message_content}))
    response.set_cookie('session_id', session_id)  # Store session ID in a cookie
    
    return response

@app.route("/askkreislaufwirtschaftsgesetz", methods=["POST"])
def ask2():
    user_message = request.json.get("message")

    # Create a message
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message,
    )

    # Generate a response
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id, assistant_id=assistant_id_kreislaufwirtschaftsgesetz
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))
    message_content = messages[0].content[0].text

    return jsonify({"response": message_content.value})


@app.route("/askbundesbodenschutzverordnung", methods=["POST"])
def ask3():
    user_message = request.json.get("message")

    # Create a message
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message,
    )

    # Generate a response
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id, assistant_id=assistant_id_bundesbodenschutzverordnung
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))
    message_content = messages[0].content[0].text

    return jsonify({"response": message_content.value})


@app.route("/asklaga_pn_98", methods=["POST"])
def ask4():
    user_message = request.json.get("message")

    # Create a message
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message,
    )

    # Generate a response
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id, assistant_id=assistant_id_laga_pn_98
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))
    message_content = messages[0].content[0].text

    return jsonify({"response": message_content.value})


@app.route("/askErsatzbaustoffverordnung", methods=["POST"])
def ask5():
    user_message = request.json.get("message")

    # Create a message
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message,
    )

    # Generate a response
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id, assistant_id=assistant_id_Ersatzbaustoffverordnung
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))
    message_content = messages[0].content[0].text

    return jsonify({"response": message_content.value})


@app.route("/askDeponieverordnung", methods=["POST"])
def ask6():
    user_message = request.json.get("message")

    # Create a message
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message,
    )

    # Generate a response
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id, assistant_id=assistant_id_Deponieverordnung
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))
    message_content = messages[0].content[0].text

    return jsonify({"response": message_content.value})
    

@app.route("/askProbenahmeprotokoll", methods=["POST"])
def ask7():
    user_message = request.json.get("message")

    # Create a message
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message,
    )

    # Generate a response
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id, assistant_id=assistant_id_Probenahmeprotokoll
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))
    message_content = messages[0].content[0].text

    return jsonify({"response": message_content.value})





if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)
