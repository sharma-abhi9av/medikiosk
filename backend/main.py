import os
import uuid
import json

from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware

from db import (
    create_tables,
    get_db_connection,
    get_conversation_history,
    save_message,
    now,
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


@app.post("/api/session/start")
def start_session(data: dict):
    session_id = str(uuid.uuid4())
    started_at = now()

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO sessions (id, patient_name, language, abha_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, data.get("patient_name"), data.get("language"), data.get("abha_id"), started_at),
    )
    conn.commit()
    conn.close()

    return {"session_id": session_id, "patient_name": data.get("patient_name"), "started_at": started_at}


@app.post("/api/consent")
def consent(data: dict):
    session_id = data["session_id"]
    consent_given = data.get("consent_given", False)
    logged_at = now()

    conn = get_db_connection()
    conn.execute(
        "UPDATE sessions SET consent_given = ?, consent_timestamp = ? WHERE id = ?",
        (1 if consent_given else 0, logged_at, session_id),
    )
    conn.commit()
    conn.close()

    # Audit trail — plain text log, this is the security/compliance evidence for the pitch
    with open("consent_audit.log", "a") as f:
        f.write(f"[{logged_at}] session {session_id}: consent_given={consent_given}\n")

    return {"status": "ok", "logged_at": logged_at}



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
        conn = get_db_connection()
        conn.execute("UPDATE sessions SET status = 'awaiting_documents' WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()

    return result


@app.post("/api/upload-document")
async def upload_document(session_id: str = Form(...), file: UploadFile = None):
    document_id = str(uuid.uuid4())
    saved_path = os.path.join(UPLOAD_DIR, f"{document_id}_{file.filename}")

    contents = await file.read()
    with open(saved_path, "wb") as f:
        f.write(contents)

    from ocr_engine import extract_prescription_data
    result = extract_prescription_data(saved_path)

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO documents (id, session_id, filename, extracted_text, structured_json, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (document_id, session_id, file.filename, result["raw_text"], json.dumps(result["structured"]), now()),
    )
    conn.commit()
    conn.close()

    return {"document_id": document_id, "extracted_text": result["raw_text"], "structured": result["structured"]}


@app.get("/api/summary/{session_id}")
def summary(session_id: str):
    from summary_engine import generate_summary
    result = generate_summary(session_id)

    conn = get_db_connection()
    docs = conn.execute(
        "SELECT id AS document_id, extracted_text, structured_json FROM documents WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    conn.close()

    documents = [
        {"document_id": d["document_id"], "extracted_text": d["extracted_text"], "structured": json.loads(d["structured_json"])}
        for d in docs
    ]

    return {"session_id": session_id, "documents": documents, "generated_at": now(), **result}


@app.get("/api/sessions")
def sessions():
    conn = get_db_connection()
    rows = conn.execute("SELECT id AS session_id, patient_name, created_at AS started_at, status FROM sessions ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]
