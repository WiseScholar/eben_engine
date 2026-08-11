import json
import random
import re
import mysql.connector
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv

# --- PYTORCH IMPORTS ---
import torch
from model import NeuralNet
from nltk_utils import bag_of_words, tokenize

# --- GENERATIVE AI IMPORTS (GEMINI NEW SDK) ---
from google import genai

app = Flask(__name__)
CORS(app)

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "database": os.getenv("DB_NAME"),
}

# --- CONFIGURE GEMINI LLM CLIENT ---
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    llm_client = genai.Client(api_key=gemini_api_key)
else:
    llm_client = None
    print("WARNING: GEMINI_API_KEY not found in .env. Hybrid fallback will be disabled.")

# --- LOAD THE PYTORCH BRAIN ON BOOT ---
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
FILE = "data.pth"
data = torch.load(FILE, map_location=device)

input_size = data["input_size"]
hidden_size = data["hidden_size"]
output_size = data["output_size"]
all_words = data['all_words']
tags = data['tags']
model_state = data["model_state"]

model = NeuralNet(input_size, hidden_size, output_size).to(device)
model.load_state_dict(model_state)
model.eval()


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

    def process_message(self, user_message, user_name, context=None):
        if context is None:
            context = {}

        first_name = user_name.split()[0] if user_name else "Scholar"

        if not user_message.strip():
            return f"I didn't quite catch that, {first_name}. Could you provide a bit more detail?"

        # 1. NLP Pipeline: Tokenize and convert to Bag of Words
        sentence = tokenize(user_message)
        X = bag_of_words(sentence, all_words)
        X = X.reshape(1, X.shape[0])
        X = torch.from_numpy(X).to(device)

        # 2. PyTorch Inference
        output = model(X)
        _, predicted = torch.max(output, dim=1)
        tag = tags[predicted.item()]

        # 3. Calculate Confidence Score
        probs = torch.softmax(output, dim=1)
        prob = probs[0][predicted.item()]
        confidence_score = prob.item() * 100

        # Save cleaned string to DB logs
        clean_db_string = " ".join(sentence).lower()
        self.log_to_db(user_name, user_message, clean_db_string, tag, confidence_score)

        # 4. Handle Guest Overrides
        if user_name == "Guest" and tag in ["booking_inquiry", "availability"]:
            return "Welcome to the Sanctuary! To view available suites or apply for a room, please click the 'Register' or 'Apply Now' button on the navigation bar to create an account."

        # 5. LLM Hybrid Fallback (Confidence < 75.0)
        if confidence_score < 75.0:
            print(f"[HYBRID SHIFT] PyTorch confidence low ({confidence_score:.1f}%). Routing to Gemini LLM with context...")

            if llm_client:
                booking_status = context.get('booking_status', 'No Active Booking')
                room_number = context.get('room_number', 'Unassigned')
                block_name = context.get('block_name', 'Unassigned')
                amount_due = context.get('amount_due', 0)
                open_tickets = context.get('open_tickets', 0)

                prompt = f"""
                You are E.B.E.N. (Electronic Broadcast & Engagement Nexus), the highly intelligent, hospitable, and helpful digital assistant for the Eco Green Sanctuary student hostel at Ghana Communication Technology University (GCTU).
                You are currently talking to a scholar named {first_name}.

                LIVE STUDENT CONTEXT:
                - Booking Status: {booking_status}
                - Assigned Room: Room {room_number} ({block_name})
                - Outstanding Balance: GHS {amount_due}
                - Active Tickets/Requests: {open_tickets}

                Strict Rules:
                1. Keep your response brief, friendly, natural, and conversational (1 to 3 sentences max).
                2. Do NOT invent any hostel rules, prices, or bank account numbers.
                3. Use the LIVE STUDENT CONTEXT above to answer questions accurately if the student asks about their room, booking status, or tickets.
                4. If the question is completely unrelated to the hostel or academic living, politely guide them back to Sanctuary operations.

                Student says: "{user_message}"
                """

                try:
                    response = llm_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                    )
                    return response.text.strip()
                except Exception as e:
                    print(f"LLM Error: {e}")
                    return f"I'm picking up your signal, {first_name}, but my conversational circuits are experiencing high latency. Could you rephrase that for me?"
            else:
                return f"I'm picking up your signal, {first_name}, but I want to be precise. Could you rephrase your question?"

        # 6. Core Logic Response (Confidence >= 75.0)
        for intent in self.memory["intents"]:
            if tag == intent["tag"]:
                raw_response = random.choice(intent["responses"])

                if raw_response == "SYSTEM_DIAGNOSTIC_TRIGGER_UPLOAD":
                    return f"I noticed you're having trouble with file uploads, {first_name}. Please ensure your receipt image is in JPG or PNG format and under 5MB. If it persists, try clearing your browser cache."

                if "{name}" in raw_response:
                    return raw_response.replace("{name}", first_name)

                if tag == "greeting":
                    return raw_response.replace("Scholar", first_name)

                return raw_response.replace("{name}", "").strip()


eben = EbenEngine("intents.json")


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({
        "status": "online",
        "engine": "E.B.E.N. v4.0 (Hybrid PyTorch + Gemini Live Context)",
        "message": "Neural systems and LLM context engine active."
    }), 200


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    message = data.get("message", "")
    user_name = data.get("user_name", "Scholar")
    context = data.get("context", {})

    bot_response = eben.process_message(message, user_name, context)
    return jsonify({"response": bot_response, "signature": "E.B.E.N. v4"})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5050, debug=False)