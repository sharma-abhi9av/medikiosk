import os
import uuid

from fastapi import FastAPI, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware

from db import (
    create_tables,
    get_conversation_history,
    save_message,
    now,
    save_new_session,
    log_session_consent,
    update_session_status,
    save_document,
    get_session_documents,
    get_all_sessions,
    get_summary,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

create_tables()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. POST /api/session/start
# ---------------------------------------------------------------------------
@app.post("/api/session/start")
def start_session(data: dict):
    session_id = str(uuid.uuid4())
    started_at = now()

    save_new_session(session_id, data.get("patient_name"), data.get("language"), data.get("abha_id"), started_at)

    return {"session_id": session_id, "patient_name": data.get("patient_name"), "started_at": started_at}


# ---------------------------------------------------------------------------
# 2. POST /api/consent
# ---------------------------------------------------------------------------
@app.post("/api/consent")
def consent(data: dict):
    session_id = data["session_id"]
    consent_given = data.get("consent_given", False)
    logged_at = now()

    log_session_consent(session_id, consent_given, logged_at)

    # Audit trail — plain text log, this is the security/compliance evidence for the pitch
    with open("consent_audit.log", "a") as f:
        f.write(f"[{logged_at}] session {session_id}: consent_given={consent_given}\n")

    return {"status": "ok", "logged_at": logged_at}


# ---------------------------------------------------------------------------
# 3. POST /api/converse  — needs ai_engine.get_next_question()
# ---------------------------------------------------------------------------
@app.post("/api/converse")
def converse(data: dict):
    session_id = data["session_id"]
    patient_answer = data["patient_answer"]

    history = get_conversation_history(session_id)
    current_stage = history[-1]["stage"] if history else "chief_complaint"

    # Import here (not at the top of the file) so the rest of the server still
    # runs even before ai_engine.py exists or has a bug — only this route fails.
    from ai_engine import get_next_question
    result = get_next_question(history, patient_answer, current_stage)

    save_message(session_id, "patient", patient_answer, current_stage)
    save_message(session_id, "ai", result["ai_question"], result["stage"])

    if result.get("is_complete"):
        update_session_status(session_id, "awaiting_documents")

    return result


# ---------------------------------------------------------------------------
# 4. POST /api/upload-document  — needs ocr_engine.extract_prescription_data()
# ---------------------------------------------------------------------------
@app.post("/api/upload-document")
async def upload_document(session_id: str = Form(...), file: UploadFile = File(...)):
    document_id = str(uuid.uuid4())
    saved_path = os.path.join(UPLOAD_DIR, f"{document_id}_{file.filename}")

    contents = await file.read()
    with open(saved_path, "wb") as f:
        f.write(contents)

    from ocr_engine import extract_prescription_data
    result = extract_prescription_data(saved_path)

    save_document(document_id, session_id, file.filename, result["raw_text"], result["structured"], now())

    return {"document_id": document_id, "extracted_text": result["raw_text"], "structured": result["structured"]}


# ---------------------------------------------------------------------------
# 5. GET /api/summary/{session_id}  — needs summary_engine.generate_summary()
# ---------------------------------------------------------------------------
@app.get("/api/summary/{session_id}")
def summary(session_id: str):
    # Only generate a new summary if one doesn't already exist for this patient —
    # this is what makes the patient's confirmed summary and the doctor's view
    # the SAME summary, instead of a fresh AI generation every time this is viewed.
    existing = get_summary(session_id)
    if existing:
        result = existing
    else:
        from summary_engine import generate_summary
        result = generate_summary(session_id)

    documents = get_session_documents(session_id)

    return {"session_id": session_id, "documents": documents, "generated_at": now(), **result}


# ---------------------------------------------------------------------------
# 6. GET /api/sessions
# ---------------------------------------------------------------------------
@app.get("/api/sessions")
def sessions():
    return get_all_sessions()
