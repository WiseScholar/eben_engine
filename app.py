import json
import random
import re
import mysql.connector
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv

# --- NEW PYTORCH IMPORTS ---
import torch
from model import NeuralNet
from nltk_utils import bag_of_words, tokenize

# --- GENERATIVE AI IMPORTS (NEW SDK) ---
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

# --- LOAD THE BRAIN ONLY ONCE ON BOOT ---
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
model.eval() # Set the model to evaluation (testing) mode

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

    def process_message(self, user_message, user_name):
        first_name = user_name.split()[0] if user_name else "Scholar"

        if not user_message.strip():
            return f"I didn't quite catch that, {first_name}. Could you provide a bit more detail?"

        # 1. NLP Pipeline: Tokenize and convert to Bag of Words
        sentence = tokenize(user_message)
        X = bag_of_words(sentence, all_words)
        X = X.reshape(1, X.shape[0])
        X = torch.from_numpy(X).to(device)

        # 2. PyTorch Inference (The Thinking Phase)
        output = model(X)
        _, predicted = torch.max(output, dim=1)
        tag = tags[predicted.item()]

        # 3. Calculate Confidence Score
        probs = torch.softmax(output, dim=1)
        prob = probs[0][predicted.item()]
        confidence_score = prob.item() * 100 # Convert to percentage like 99.4

        # Save a basic cleaned string for your DB records
        clean_db_string = " ".join(sentence).lower()
        self.log_to_db(user_name, user_message, clean_db_string, tag, confidence_score)

        # 4. Handle Guest Overrides
        if user_name == "Guest" and tag == "booking_inquiry":
            return "I see you're visiting! To book a room, you first need to create an account. Once you register and log in, you can select your suite directly from the dashboard."

        if user_name == "Guest" and tag == "guest_registration":
            return "Welcome to the Sanctuary! To begin, click the 'Register' button on the navigation bar. Once you create an account, you can log in to view available suites."

        # 5. The Confidence Threshold (The LLM Hybrid Fallback)
        if confidence_score < 75.0:
            print(f"[HYBRID SHIFT] PyTorch confidence too low ({confidence_score:.1f}%). Routing to LLM...")
            
            if llm_client:
                # The System Persona
                prompt = f"""
                You are E.B.E.N. (Electronic Broadcast & Engagement Nexus), the highly intelligent, slightly witty, and helpful digital assistant for the Eco Green Sanctuary student hostel at Ghana Communication Technology University (GCTU).
                You are currently talking to a scholar named {first_name}.
                
                Strict Rules:
                1. Keep your response brief, friendly, and conversational (under 3 sentences).
                2. Do NOT invent any hostel rules, prices, or bank account numbers. 
                3. If the student asks a specific technical question about the hostel that you don't know, casually tell them to rephrase it so your core systems can process it.
                
                Student says: "{user_message}"
                """
                
                try:
                    # Using the new SDK syntax to generate content
                    response = llm_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                    )
                    return response.text.strip()
                except Exception as e:
                    print(f"LLM Error: {e}")
                    return f"I'm picking up your signal, {first_name}, but my conversational circuits are a bit overloaded. Could you rephrase that?"
            else:
                # Failsafe if the API key isn't configured yet
                return f"I'm picking up your signal, {first_name}, but I want to be precise. Could you rephrase that?"

        # 6. Fetch the Response (High Confidence Core Logic)
        for intent in self.memory["intents"]:
            if tag == intent["tag"]:
                raw_response = random.choice(intent["responses"])

                # --- PHASE 5 HOOK: The Problem Solving Agent ---
                if raw_response == "SYSTEM_DIAGNOSTIC_TRIGGER_UPLOAD":
                    return f"[AGENT DIAGNOSTIC TRIGGERED] Give me a moment, {first_name}, I am checking the server logs for your receipt upload error..."
                
                # Standard Text Replacements
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
        "engine": "E.B.E.N. v4.0 (Hybrid PyTorch+LLM)",
        "message": "Neural systems and LLM fallback stable."
    }), 200

@app.route('/ai/briefing', methods=['POST'])
def generate_briefing():
    data = request.get_json()
    on_site = data.get('on_site')
    total = data.get('total')
    recent = data.get('recent')
    days_left = data.get('days_left')

    prompt = f"""
    You are E.B.E.N., the Sanctuary Intelligence. 
    Give a warm, professional, and natural briefing to the Chief Warden.
    Stats: {on_site} scholars are home out of {total}. 
    Recently arrived: {recent}. 
    Days remaining in cycle: {days_left}.
    Keep it under 3 sentences. Be witty but professional.
    """

    response = model.generate_content(prompt)
    
    return jsonify({
        "briefing": response.text
    })

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message", "")
    user_name = data.get("user_name", "Scholar")

    bot_response = eben.process_message(message, user_name)
    return jsonify({"response": bot_response, "signature": "E.B.E.N. v4"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5050, debug=False)