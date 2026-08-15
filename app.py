import json
import os
import mysql.connector
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# --- GENERATIVE AI IMPORTS (GEMINI SDK) ---
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
        self.chat_memory = {}  # Short-term memory dictionary for active sessions
        self.knowledge_base = {}
        
        if os.path.exists(knowledge_path):
            with open(knowledge_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                self.intents = data.get("intents", [])
                self.raw_knowledge_text = self._compile_knowledge_base(self.intents)
        else:
            self.intents = []
            self.raw_knowledge_text = "Standard Eco Green Sanctuary Operational Rules."

    def _compile_knowledge_base(self, intents):
        """Compiles intents.json into structured rules for the LLM system prompt."""
        compiled_sections = []
        for item in intents:
            tag = item.get("tag", "general")
            responses = " ".join(item.get("responses", []))
            # Clean template variables but LEAVE {name} intact for dynamic replacement later
            cleaned_resp = responses.replace("SYSTEM_DIAGNOSTIC_TRIGGER_UPLOAD", "Advise student to use JPG/PNG under 5MB.")
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

        # 1. Manage Short-Term Memory (Keep last 4 interactions)
        if user_name not in self.chat_memory:
            self.chat_memory[user_name] = []
            
        memory_context = ""
        if self.chat_memory[user_name]:
            memory_context = "\n### RECENT CONVERSATION HISTORY:\n"
            for turn in self.chat_memory[user_name]:
                memory_context += f"{turn['role']}: {turn['text']}\n"

        # 2. Extract student live database variables
        booking_status = context.get("booking_status", "No Active Booking")
        room_number = context.get("room_number", "Unassigned")
        block_name = context.get("block_name", "Unassigned")
        amount_due = context.get("amount_due", 0)
        open_tickets = context.get("open_tickets", 0)

        # 3. Dynamically inject the student's name into the knowledge base
        personalized_knowledge = self.raw_knowledge_text.replace("{name}", first_name)

        # Primary LLM Pipeline
        if llm_client:
            system_instruction = f"""
You are E.B.E.N. (Electronic Broadcast & Engagement Nexus), the dedicated AI assistant for the Eco Green Sanctuary student residency at Ghana Communication Technology University (GCTU).
You are conversing with: {first_name} (Full Name: {user_name}). Address them exclusively as {first_name}.

### LIVE DATABASE CONTEXT FOR THIS USER:
- Current Booking Status: {booking_status}
- Room Assigned: Room {room_number} ({block_name})
- Outstanding Balance: GHS {amount_due}
- Active Maintenance/Special Requests: {open_tickets}

### RESIDENCY KNOWLEDGE BASE & OFFICIAL PROTOCOLS:
{personalized_knowledge}
{memory_context}

### CONVERSATIONAL RULES & GUARDRAILS:
1. Tone: Hospitable, intelligent, concise, clear, and reassuring.
2. Response Length: Keep responses within 1 to 3 natural sentences. Do not cut off mid-sentence.
3. Accuracy: NEVER invent bank account numbers, prices, or hostel policies outside the knowledge base.
4. Context Usage: If the user asks about their specific room, balance, booking, or tickets, prioritize the Live Database Context above.
5. Unknown Questions: If the user asks something not covered in the knowledge base (like changing passwords), politely inform them to check their dashboard settings or contact administration.
"""

            try:
                response = llm_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.3, 
                        max_output_tokens=300,
                    ),
                )
                bot_reply = response.text.strip()
                self.log_to_db(user_name, user_message, user_message.lower(), "gemini_first", 100)
                
                # Update Memory
                self.chat_memory[user_name].append({"role": first_name, "text": user_message})
                self.chat_memory[user_name].append({"role": "E.B.E.N.", "text": bot_reply})
                
                # Prevent memory from growing indefinitely (keep only last 4 messages / 2 turns)
                if len(self.chat_memory[user_name]) > 4:
                    self.chat_memory[user_name] = self.chat_memory[user_name][-4:]

                return bot_reply

            except Exception as e:
                print(f"Gemini API Exception: {e}")
                
        # Failsafe Local Fallback (If API is unreachable)
        self.log_to_db(user_name, user_message, user_message.lower(), "offline_fallback", 50)
        return (
            f"I have received your request, {first_name}, but my real-time link is experiencing latency. "
            "Please check your student dashboard or submit a ticket through the Management Desk if urgent."
        )


# Initialize Engine with knowledge base
eben = EbenEngine("intents.json")


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({
        "status": "online",
        "engine": "E.B.E.N. v5.1 (LLM-First Architecture with Memory)",
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
    return jsonify({"response": bot_response, "signature": "E.B.E.N. v5.1"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)