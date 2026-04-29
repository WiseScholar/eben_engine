import json
import random
import re
import mysql.connector # Added this
from flask import Flask, request, jsonify
from flask_cors import CORS
from thefuzz import fuzz

app = Flask(__name__)
CORS(app)

# --- DATABASE CONFIGURATION ---
# Get these details from your DirectAdmin MySQL Management page
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

    def log_to_db(self, user_msg, clean_msg, intent, score):
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            query = "INSERT INTO eben_chat_logs (user_message, cleaned_message, matched_intent, confidence_score) VALUES (%s, %s, %s, %s)"
            cursor.execute(query, (user_msg, clean_msg, intent, int(score)))
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

    def process_message(self, user_message):
        clean_user_message = self.clean_text(user_message)
        if not clean_user_message:
             return "I didn't quite catch the specifics. Could you provide a bit more detail?"

        best_intent = None
        highest_confidence = 0
        
        for intent in self.memory['intents']:
            for pattern in intent['patterns']:
                clean_pattern = self.clean_text(pattern)
                confidence = fuzz.token_set_ratio(clean_user_message, clean_pattern)
                if confidence > highest_confidence:
                    highest_confidence = confidence
                    best_intent = intent

        matched_tag = best_intent['tag'] if best_intent else "unmatched"
        
        # --- LOG TO SQL INSTEAD OF CSV ---
        self.log_to_db(user_message, clean_user_message, matched_tag, highest_confidence)

        if highest_confidence < 60:
            return "I'm picking up your signal, but I want to be precise. Could you rephrase that?"
            
        return random.choice(best_intent['responses'])

eben = EbenEngine('intents.json')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    bot_response = eben.process_message(data.get('message', ''))
    return jsonify({"response": bot_response, "signature": "E.B.E.N."})

if __name__ == '__main__':
    app.run(debug=False)