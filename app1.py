import json
import random
import re
import mysql.connector
from flask import Flask, request, jsonify
from flask_cors import CORS
from thefuzz import fuzz
import os
from dotenv import load_dotenv

app = Flask(__name__)
CORS(app)

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "database": os.getenv("DB_NAME"),
}

STOP_WORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "am",
    "i",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "to",
    "do",
    "does",
    "did",
    "can",
    "could",
    "would",
    "should",
    "for",
    "of",
    "with",
    "as",
    "me",
    "my",
    "how",
    "what",
    "where",
    "when",
    "why",
    "in",
    "on",
    "at",
    "please",
    "can",
    "direct",
}


class EbenEngine:
    def __init__(self, knowledge_path):
        with open(knowledge_path, "r") as file:
            self.memory = json.load(file)

    def log_to_db(self, user_name, user_msg, clean_msg, intent, score):
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            query = "INSERT INTO eben_chat_logs (user_name, user_message, cleaned_message, matched_intent, confidence_score) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(query, (user_name, user_msg, clean_msg, intent, int(score)))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Database Logging Error: {e}")

    def clean_text(self, text):
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        words = text.split()
        filtered_words = [w for w in words if w not in STOP_WORDS]
        return " ".join(filtered_words)

    def process_message(self, user_message, user_name):
        clean_user_message = self.clean_text(user_message)
        first_name = user_name.split()[0] if user_name else "Scholar"

        if not clean_user_message:
            return f"I didn't quite catch that, {first_name}. Could you provide a bit more detail?"

        best_intent = None
        highest_confidence = 0

        for intent in self.memory["intents"]:
            for pattern in intent["patterns"]:
                clean_pattern = self.clean_text(pattern)
                confidence = fuzz.token_set_ratio(clean_user_message, clean_pattern)
                if confidence > highest_confidence:
                    highest_confidence = confidence
                    best_intent = intent

        matched_tag = best_intent["tag"] if best_intent else "unmatched"

        self.log_to_db(
            user_name, user_message, clean_user_message, matched_tag, highest_confidence
        )

        if user_name == "Guest" and matched_tag == "booking_inquiry":
            return "I see you're visiting! To book a room, you first need to create an account. Once you register and log in, you can select your suite directly from the dashboard."

        if user_name == "Guest" and matched_tag == "guest_registration":
            return "Welcome to the Sanctuary! To begin, click the 'Register' button on the navigation bar. Once you create an account, you can log in to view available suites."

        if highest_confidence < 60:
            return f"I'm picking up your signal, {first_name}, but I want to be precise. Could you rephrase that?"

        raw_response = random.choice(best_intent["responses"])

        if "{name}" in raw_response:
            return raw_response.replace("{name}", first_name)

        if matched_tag == "greeting":
            return raw_response.replace("Scholar", first_name)

        return raw_response.replace("{name}", "").strip()


eben = EbenEngine("intents.json")


@app.route("/api/status", methods=["GET"])
def status():
    return (
        jsonify(
            {
                "status": "online",
                "engine": "E.B.E.N. v2.1",
                "message": "Neural systems stable.",
            }
        ),
        200,
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message", "")
    user_name = data.get("user_name", "Scholar")  # Captured from Laravel payload

    bot_response = eben.process_message(message, user_name)
    return jsonify({"response": bot_response, "signature": "E.B.E.N."})


if __name__ == "__main__":
    app.run(debug=False)
