import json
import random
import csv
import os
import re
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from thefuzz import fuzz

app = Flask(__name__)
CORS(app)

# The Stop Words Dictionary: E.B.E.N. will ignore these to focus on the actual intent
STOP_WORDS = {"a", "an", "the", "is", "are", "am", "i", "you", "he", "she", "it", "we", "they", 
              "to", "do", "does", "did", "can", "could", "would", "should", "for", "of", "with", 
              "as", "me", "my", "how", "what", "where", "when", "why", "in", "on", "at", "please", "can", "direct"}

class EbenEngine:
    def __init__(self, knowledge_path, log_path):
        self.log_path = log_path
        
        with open(knowledge_path, 'r') as file:
            self.memory = json.load(file)
            
        if not os.path.exists(self.log_path):
            with open(self.log_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'user_message', 'cleaned_message', 'matched_intent', 'confidence_score'])

    def clean_text(self, text):
        # Lowercase and remove punctuation
        text = text.lower().strip()
        text = re.sub(r'[^\w\s]', '', text)
        # Remove stop words
        words = text.split()
        filtered_words = [w for w in words if w not in STOP_WORDS]
        # Rejoin into a string
        return " ".join(filtered_words)

    def log_chat(self, user_message, cleaned_message, matched_intent, confidence_score):
        with open(self.log_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_message, cleaned_message, matched_intent, confidence_score])

    def process_message(self, user_message):
        # Pass input through the Stop-Word filter
        clean_user_message = self.clean_text(user_message)
        
        # If they only typed stop words (e.g., "how do i"), ask for clarification
        if not clean_user_message:
             return "I didn't quite catch the specifics of your request. Could you provide a bit more detail?"

        best_intent = None
        highest_confidence = 0
        
        for intent in self.memory['intents']:
            for pattern in intent['patterns']:
                # Filter the patterns too!
                clean_pattern = self.clean_text(pattern)
                
                # Math is now strictly focused on the core verbs/nouns
                confidence = fuzz.token_set_ratio(clean_user_message, clean_pattern)
                
                if confidence > highest_confidence:
                    highest_confidence = confidence
                    best_intent = intent

        matched_tag = best_intent['tag'] if best_intent else "unmatched"
        self.log_chat(user_message, clean_user_message, matched_tag, highest_confidence)

        # Confidence Threshold
        if highest_confidence < 60:
            return "I am picking up your signal, but I want to be absolutely precise. Could you rephrase your question slightly?"
            
        return random.choice(best_intent['responses'])

eben = EbenEngine('intents.json', 'chat_training_logs.csv')

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({"status": "E.B.E.N. Core Online", "version": "2.1"})

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({"error": "No message payload detected."}), 400
        
    bot_response = eben.process_message(data['message'])
    
    return jsonify({
        "response": bot_response,
        "signature": "E.B.E.N."
    })

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5050)