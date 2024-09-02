from flask import Flask, request, jsonify, render_template
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("OPENAI_API_KEY")
assistant_id = os.getenv("ASSISTANT_ID")

client = OpenAI(api_key=key)
app = Flask(__name__)

thread = client.beta.threads.create()

@app.route("/")
def index():
    return render_template("index1.html")

@app.route("/ask", methods=["POST"])
def ask():
    user_message = request.json.get("message")

    # Create a message
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message,
    )

    # Generate a response
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id, assistant_id=assistant_id
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))
    message_content = messages[0].content[0].text

    return jsonify({"response": message_content.value})

if __name__ == "__main__":
    app.run(debug=True)
