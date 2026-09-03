import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# OpenRouter speaks the same API shape as OpenAI, you just point the client
# at OpenRouter's URL and use an OpenRouter key instead of an OpenAI one.
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# Try these in order. If the first one fails (rate-limited, deprecated, key
# issue, whatever), fall through to the next before giving up entirely.
# Check your OpenRouter dashboard for current free-tier model names — these
# change over time, this list is a reasonable starting point, not gospel.
MODEL_FALLBACK_CHAIN = [
    "openrouter/free",
    "google/gemini-2.0-flash-exp:free",
    "mistralai/mistral-7b-instruct:free",
]

STAGES = ["chief_complaint", "hpi", "past_history", "drug_allergy"]

SYSTEM_PROMPT = """You are a clinical intake assistant conducting a structured pre-consultation
history interview with a patient in an Indian hospital OPD. Ask ONE question
at a time. Follow this order:

1. Chief Complaint — what is the main problem today?
2. History of Present Illness — use the SOCRATES framework (Site, Onset,
   Character, Radiation, Associated symptoms, Timing, Exacerbating/relieving
   factors, Severity). Ask 2-3 targeted follow-ups, not all 8 letters.
3. Past Medical/Surgical History — prior conditions, surgeries, hospitalizations.
4. Drug & Allergy History — current medications, known allergies.

Ask no more than 2-3 questions per stage. Keep questions short, plain-language,
and empathetic. After Drug & Allergy History is covered, respond with exactly:
"Thank you, I have everything I need."
"""


def _history_to_text(conversation_history):
    """Turns the list-of-dicts conversation_history into one readable text block
    for the AI model to read, in order."""
    if not conversation_history:
        return "(This is the start of the conversation — no messages yet.)"
    lines = []
    for msg in conversation_history:
        speaker = "AI" if msg.get("role") == "ai" else "Patient"
        lines.append(f"{speaker}: {msg.get('message', '')}")
    return "\n".join(lines)


def _get_next_stage(conversation_history, current_stage):
    """Counts how many AI questions have been asked at the current stage.
    After 2, advances to the next stage. After the last stage, marks complete."""
    count = sum(
        1 for msg in conversation_history
        if msg.get("stage") == current_stage and msg.get("role") == "ai"
    )
    if count >= 2:
        idx = STAGES.index(current_stage)
        if idx + 1 < len(STAGES):
            return STAGES[idx + 1], False
        else:
            return "complete", True
    return current_stage, False


def _call_model_with_fallback(messages):
    """Tries each model in MODEL_FALLBACK_CHAIN in order. Returns the first
    successful reply's text. Prints every model's failure as it happens (not
    just the last one) so you can see exactly which models are down/renamed.
    Raises the last error if every model fails, so the caller's own except
    block can catch it and return a safe fallback."""
    last_error = None
    for model_name in MODEL_FALLBACK_CHAIN:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                timeout=15,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[ai_engine] model '{model_name}' failed: {e}")
            last_error = e
            continue  # try the next model in the chain
    raise last_error


def get_next_question(conversation_history, patient_answer, stage):
    """
    Inputs:
      conversation_history — list of dicts, e.g. [{"role": "ai", "message": "...", "stage": "..."}, ...]
      patient_answer       — string, what the patient just said
      stage                — string, one of STAGES

    Returns:
      {"ai_question": str, "stage": str, "is_complete": bool}
    """
    try:
        history_text = _history_to_text(conversation_history)

        user_message = (
            f"Conversation so far:\n{history_text}\n\n"
            f"Patient's latest answer: {patient_answer}\n\n"
            f"Respond with ONLY the next question (or the completion message). "
            f"Do not add extra commentary."
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        ai_reply = _call_model_with_fallback(messages)

        # Decide completion/stage ourselves — don't trust the model to track this.
        if "thank you, i have everything i need" in ai_reply.lower():
            return {"ai_question": ai_reply, "stage": "complete", "is_complete": True}

        next_stage, is_complete = _get_next_stage(conversation_history, stage)
        return {"ai_question": ai_reply, "stage": next_stage, "is_complete": is_complete}

    except Exception as e:
        # Never let a dropped connection or bad key crash the whole server —
        # the patient still needs a question to keep the conversation moving.
        print(f"[ai_engine] all models failed: {e}")
        return {"ai_question": "Could you tell me a little more about that?", "stage": stage, "is_complete": False}
