from flask import Flask, request, jsonify
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("OPENAI_API_KEY")
assistant_id_berater = os.getenv("ASSISTANT_ID_berater")
assistant_id_kreislaufwirtschaftsgesetz = os.getenv("ASSISTANT_ID_kreislaufwirtschaftsgesetz")
assistant_id_bundesbodenschutzverordnung = os.getenv("ASSISTANT_ID_bundesbodenschutzverordnung")
assistant_id_laga_pn_98 = os.getenv("ASSISTANT_ID_laga_pn_98")
assistant_id_Ersatzbaustoffverordnung = os.getenv("ASSISTANT_ID_Ersatzbaustoffverordnung")
assistant_id_Deponieverordnung = os.getenv("ASSISTANT_ID_Deponieverordnung")

client = OpenAI(api_key=key)
app = Flask(__name__)

thread = client.beta.threads.create()

@app.route("/")
def index():
    return render_template("index1.html")

@app.route("/askberater", methods=["POST"])
def ask1():
    user_message = request.json.get("message")

    # Create a message
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message,
    )

    # Generate a response
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id, assistant_id=assistant_id_berater
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))
    message_content = messages[0].content[0].text

    return jsonify({"response": message_content.value})


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





if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)

