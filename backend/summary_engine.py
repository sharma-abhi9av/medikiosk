import os
import json
from openai import OpenAI
from dotenv import load_dotenv

from db import get_conversation_history, get_session_documents, save_summary, now

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# Same fallback idea as ai_engine.py — openrouter/free lets OpenRouter pick a
# healthy free model automatically, with two named backups if that ever fails.
MODEL_FALLBACK_CHAIN = [
    "openrouter/free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3.5-lightning:free",
]

SUMMARY_SYSTEM_PROMPT = """You are a clinical scribe. You will be given a patient interview
transcript and, if available, text extracted from an uploaded prescription document.
Summarize this into a structured clinical note.

CRITICAL RULE: Only include information that was explicitly stated in the transcript or
document text below. Never invent, assume, or estimate any detail that was not actually
said — this includes age, gender, exact dates, severity numbers, which side of the body
(left/right) is affected, or any medical history not mentioned. If the patient did not
specify a detail (for example, which side is injured), do not guess or pick one — simply
omit that detail rather than making it up.

Respond with ONLY a JSON object (no markdown fences, no extra commentary) with exactly
these four keys:
{
  "chief_complaint": "...",
  "hpi": "...",
  "past_history": "...",
  "drug_allergy_history": "..."
}

Each value should be a short, clear clinical-note-style sentence or two, written the way
a doctor would want to read it, using ONLY what the patient or document actually stated.
If the transcript doesn't cover a section, write "Not discussed" for that key rather than
leaving it blank or guessing.
"""


def _conversation_to_text(history):
    """Same pattern as ai_engine.py — turns the list-of-dicts history into readable text."""
    if not history:
        return "(No conversation recorded.)"
    lines = []
    for msg in history:
        speaker = "AI" if msg.get("role") == "ai" else "Patient"
        lines.append(f"{speaker}: {msg.get('message', '')}")
    return "\n".join(lines)


def _documents_to_text(documents):
    """Turns the list of uploaded documents into readable text, or a clear
    'nothing uploaded' note — this matters because sending an empty string
    to the AI can cause it to invent document content that was never there."""
    if not documents:
        return "No prior documents uploaded."
    lines = []
    for doc in documents:
        meds = ", ".join(doc["structured"].get("medicines", [])) or "none listed"
        date = doc["structured"].get("date", "unknown date")
        lines.append(f"- Extracted text: {doc['extracted_text']} (medicines: {meds}, date: {date})")
    return "\n".join(lines)


def _clean_json_reply(raw_reply):
    """LLMs often wrap JSON in ```json ... ``` fences — strip those before parsing."""
    cleaned = raw_reply.strip()
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    return cleaned


def _call_model_with_fallback(messages):
    """Same pattern as ai_engine.py's _call_model_with_fallback — tries each
    model in order, prints every individual failure, raises the last error
    only if all of them fail."""
    last_error = None
    for model_name in MODEL_FALLBACK_CHAIN:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                timeout=20,
                temperature=0,  # as literal/consistent as possible — this is a clinical summary, not creative writing
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[summary_engine] model '{model_name}' failed: {e}")
            last_error = e
            continue
    raise last_error


def generate_summary(session_id):
    """
    Input: session_id (string)

    Reads the full conversation and any uploaded documents for this patient
    from the database, asks the AI to produce a structured clinical summary,
    saves it into the summaries table, and returns it.

    Returns:
      {"chief_complaint": str, "hpi": str, "past_history": str, "drug_allergy_history": str}
    """
    history = get_conversation_history(session_id)
    documents = get_session_documents(session_id)

    conversation_text = _conversation_to_text(history)
    documents_text = _documents_to_text(documents)

    user_message = (
        f"Patient interview transcript:\n{conversation_text}\n\n"
        f"Uploaded document information:\n{documents_text}\n\n"
        f"Produce the structured JSON summary now."
    )

    messages = [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    fallback_result = {
        "chief_complaint": "Unable to generate summary at this time.",
        "hpi": "Not available.",
        "past_history": "Not available.",
        "drug_allergy_history": "Not available.",
    }

    try:
        raw_reply = _call_model_with_fallback(messages)
        cleaned = _clean_json_reply(raw_reply)
        result = json.loads(cleaned)

        # Make sure all 4 keys are present even if the model dropped one —
        # never let a partial AI response break the response shape downstream.
        for key in ["chief_complaint", "hpi", "past_history", "drug_allergy_history"]:
            result.setdefault(key, "Not discussed")

    except Exception as e:
        print(f"[summary_engine] failed to generate or parse summary: {e}")
        result = fallback_result

    save_summary(
        session_id,
        result["chief_complaint"],
        result["hpi"],
        result["past_history"],
        result["drug_allergy_history"],
        now(),
    )

    return result
