import json
import random
import re
import mysql.connector
from flask import Flask, request, jsonify
from flask_cors import CORS
from thefuzz import fuzz

app = Flask(__name__)
CORS(app)

DB_CONFIG = {
    'host': 'graceintltemple.org', 
    'user': 'graceintltemple_eco',
    'password': 'PpZYn46x6rxQDntmbnA5',
    'database': 'graceintltemple_eco'
}

STOP_WORDS = {"a", "an", "the", "is", "are", "am", "i", "you", "he", "she", "it", "we", "they", 
              "to", "do", "does", "did", "can", "could", "would", "should", "for", "of", "with", 
              "as", "me", "my", "how", "what", "where", "when", "why", "in", "on", "at", "please", "can", "direct"}

class EbenEngine:
    def __init__(self, knowledge_path):
        with open(knowledge_path, 'r') as file:
            self.memory = json.load(file)

    def log_to_db(self, user_name, user_msg, clean_msg, intent, score):
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            # Fixed: Added a 5th %s for the confidence_score
            query = "INSERT INTO eben_chat_logs (user_name, user_message, cleaned_message, matched_intent, confidence_score) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(query, (user_name, user_msg, clean_msg, intent, int(score)))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Database Logging Error: {e}")

    def clean_text(self, text):
        text = text.lower().strip()
        text = re.sub(r'[^\w\s]', '', text)
        words = text.split()
        filtered_words = [w for w in words if w not in STOP_WORDS]
        return " ".join(filtered_words)

    def process_message(self, user_message, user_name):
        clean_user_message = self.clean_text(user_message)
        # Extract first name (e.g., "Eben" from "Eben Tefe")
        first_name = user_name.split()[0] if user_name else "Scholar"
        
        # Handle empty/unintelligible input
        if not clean_user_message:
             return f"I didn't quite catch that, {first_name}. Could you provide a bit more detail?"

        best_intent = None
        highest_confidence = 0
        
        # Search memory for the best pattern match
        for intent in self.memory['intents']:
            for pattern in intent['patterns']:
                clean_pattern = self.clean_text(pattern)
                confidence = fuzz.token_set_ratio(clean_user_message, clean_pattern)
                if confidence > highest_confidence:
                    highest_confidence = confidence
                    best_intent = intent

        matched_tag = best_intent['tag'] if best_intent else "unmatched"
        
        # Log telemetry data to SQL
        self.log_to_db(user_name, user_message, clean_user_message, matched_tag, highest_confidence)

        # Handle low confidence / unmatched queries
        if highest_confidence < 60:
            # We only use the name here once to keep the error polite
            return f"I'm picking up your signal, {first_name}, but I want to be precise. Could you rephrase that?"
            
        # Select a random response from the matched intent
        raw_response = random.choice(best_intent['responses'])
        
        # --- SMART PERSONALIZATION LOGIC ---
        
        # 1. If we have a manual {name} placeholder, replace it and return immediately
        if "{name}" in raw_response:
            return raw_response.replace("{name}", first_name)
        
        # 2. If it's a greeting, we force the name in for a warm welcome
        if matched_tag == "greeting":
            # Replaces "Scholar" with the first name if it exists in your greeting strings
            return raw_response.replace("Scholar", first_name)

        # 3. For all other intents (pricing, rules, etc.), return the clean response
        # This prevents the name from appearing in every single bubble.
        # We also strip out any accidental {name} tags left in the JSON
        return raw_response.replace("{name}", "").strip()
    
eben = EbenEngine('intents.json')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    message = data.get('message', '')
    user_name = data.get('user_name', 'Scholar') # Captured from Laravel payload
    
    bot_response = eben.process_message(message, user_name)
    return jsonify({"response": bot_response, "signature": "E.B.E.N."})

if __name__ == '__main__':
    app.run(debug=False)