import json
import os
import mysql.connector
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

app = Flask(__name__)
CORS(app)

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "database": os.getenv("DB_NAME"),
}

# --- CONFIGURE GEMINI CLIENT ---
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    llm_client = genai.Client(api_key=gemini_api_key)
else:
    llm_client = None
    print("CRITICAL WARNING: GEMINI_API_KEY not found. Operating in emergency fallback mode.")


class EbenEngine:
    def __init__(self, knowledge_path="intents.json"):
        self.knowledge_base = {}
        if os.path.exists(knowledge_path):
            with open(knowledge_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                self.intents = data.get("intents", [])
                self.knowledge_text = self._compile_knowledge_base(self.intents)
        else:
            self.intents = []
            self.knowledge_text = "Standard Eco Green Sanctuary Operational Rules."

    def _compile_knowledge_base(self, intents):
        """Compiles intents.json into structured rules for the LLM system prompt."""
        compiled_sections = []
        for item in intents:
            tag = item.get("tag", "general")
            responses = " ".join(item.get("responses", []))
            cleaned_resp = responses.replace("{name}", "the resident").replace("SYSTEM_DIAGNOSTIC_TRIGGER_UPLOAD", "Advise student to use JPG/PNG under 5MB.")
            compiled_sections.append(f"- **{tag.upper()}**: {cleaned_resp}")
        return "\n".join(compiled_sections)

    def log_to_db(self, user_name, user_msg, clean_msg, intent="llm_generation", score=100):
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            query = """
                INSERT INTO eben_chat_logs 
                (user_name, user_message, cleaned_message, matched_intent, confidence_score) 
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(query, (user_name, user_msg, clean_msg, intent, int(score)))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Database Logging Error: {e}")

    def process_message(self, user_message, user_name, context=None):
        if context is None:
            context = {}

        first_name = user_name.split()[0] if user_name and user_name != "Guest" else "Scholar"

        if not user_message.strip():
            return f"I didn't quite catch that, {first_name}. How can I assist you with your Sanctuary residency today?"

        # Extract student live database variables
        booking_status = context.get("booking_status", "No Active Booking")
        room_number = context.get("room_number", "Unassigned")
        block_name = context.get("block_name", "Unassigned")
        amount_due = context.get("amount_due", 0)
        open_tickets = context.get("open_tickets", 0)

        # Primary LLM Pipeline
        if llm_client:
            system_instruction = f"""
You are E.B.E.N. (Electronic Broadcast & Engagement Nexus), the dedicated AI assistant for the Eco Green Sanctuary student residency at Ghana Communication Technology University (GCTU).
You are conversing with: {first_name} (Full Name: {user_name}).

### LIVE DATABASE CONTEXT FOR THIS USER:
- Current Booking Status: {booking_status}
- Room Assigned: Room {room_number} ({block_name})
- Outstanding Balance: GHS {amount_due}
- Active Maintenance/Special Requests: {open_tickets}

### RESIDENCY KNOWLEDGE BASE & OFFICIAL PROTOCOLS:
{self.knowledge_text}

### CONVERSATIONAL RULES & GUARDRAILS:
1. Tone: Hospitable, intelligent, concise, clear, and reassuring.
2. Response Length: Keep responses within 1 to 3 natural sentences.
3. Accuracy: NEVER invent bank account numbers, prices, or hostel policies outside the knowledge base.
4. Context Usage: If the user asks about their specific room, balance, booking, or tickets, prioritize the Live Database Context above.
5. Off-Topic Inquiries: If the student asks about non-hostel or non-academic matters, provide a brief courteous remark and gently guide them back to Sanctuary operations.
6. Guest Policy: If the user is 'Guest' and asks about room bookings or availability, instruct them to click 'Register' / 'Apply Now' to create an account.
"""

            try:
                response = llm_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.3,
                        max_output_tokens=250,
                    ),
                )
                bot_reply = response.text.strip()
                self.log_to_db(user_name, user_message, user_message.lower(), "gemini_first", 100)
                return bot_reply

            except Exception as e:
                print(f"Gemini API Exception: {e}")

        self.log_to_db(user_name, user_message, user_message.lower(), "offline_fallback", 50)
        return (
            f"I have received your request, {first_name}, but my real-time link is experiencing latency. "
            "Please check your student dashboard or submit a ticket through the Management Desk if urgent."
        )

eben = EbenEngine("intents.json")


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({
        "status": "online",
        "engine": "E.B.E.N. v5.0 (LLM-First Architecture)",
        "gemini_active": llm_client is not None,
        "message": "Direct LLM reasoning and real-time student context active."
    }), 200


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    message = data.get("message", "")
    user_name = data.get("user_name", "Scholar")
    context = data.get("context", {})

    bot_response = eben.process_message(message, user_name, context)
    return jsonify({"response": bot_response, "signature": "E.B.E.N. v5"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)