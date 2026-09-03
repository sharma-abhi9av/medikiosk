import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = "medikiosk.db"


def get_db_connection():
    """Every other file uses this same function to talk to the database.
    row_factory lets you access columns by name, e.g. row['patient_name'] instead of row[1]."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    """Run once, when the app starts. Creates the 4 tables if they don't already exist —
    safe to call every time the server starts, it won't wipe existing data."""
    conn = get_db_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            patient_name TEXT,
            language TEXT,
            abha_id TEXT,
            consent_given INTEGER DEFAULT 0,
            consent_timestamp TEXT,
            status TEXT DEFAULT 'in_progress',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            message TEXT,
            stage TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            filename TEXT,
            extracted_text TEXT,
            structured_json TEXT,
            uploaded_at TEXT
        );
        CREATE TABLE IF NOT EXISTS summaries (
            session_id TEXT PRIMARY KEY,
            chief_complaint TEXT,
            hpi TEXT,
            past_history TEXT,
            drug_allergy_history TEXT,
            generated_at TEXT
        );
    """)
    conn.commit()
    conn.close()


def now():
    """One shared helper so every timestamp in the app is formatted the same way."""
    return datetime.now(timezone.utc).isoformat()


def get_conversation_history(session_id):
    """Returns every message for this patient, in order, as a list of dicts.
    This is exactly what ai_engine.get_next_question()'s conversation_history input looks like,
    and what summary_engine.generate_summary() reads to rebuild the conversation."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT role, message, stage FROM conversation_messages WHERE session_id = ? ORDER BY id",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_message(session_id, role, message, stage):
    """Called every time the patient answers or the AI asks something — one new row per message."""
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO conversation_messages (session_id, role, message, stage, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, message, stage, now())
    )
    conn.commit()
    conn.close()


# ---- New helpers, moved in from main.py so ALL raw SQL lives only here ----

def save_new_session(session_id, patient_name, language, abha_id, started_at):
    """Called by POST /api/session/start — inserts one new patient visit row."""
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO sessions (id, patient_name, language, abha_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, patient_name, language, abha_id, started_at),
    )
    conn.commit()
    conn.close()


def log_session_consent(session_id, consent_given, logged_at):
    """Called by POST /api/consent — records whether/when the patient consented."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE sessions SET consent_given = ?, consent_timestamp = ? WHERE id = ?",
        (1 if consent_given else 0, logged_at, session_id),
    )
    conn.commit()
    conn.close()


def update_session_status(session_id, status):
    """Called by POST /api/converse once is_complete is True — marks the visit's current stage."""
    conn = get_db_connection()
    conn.execute("UPDATE sessions SET status = ? WHERE id = ?", (status, session_id))
    conn.commit()
    conn.close()


def save_document(document_id, session_id, filename, raw_text, structured_dict, uploaded_at):
    """Called by POST /api/upload-document — saves what OCR extracted from one uploaded photo."""
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO documents (id, session_id, filename, extracted_text, structured_json, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (document_id, session_id, filename, raw_text, json.dumps(structured_dict), uploaded_at),
    )
    conn.commit()
    conn.close()


def get_session_documents(session_id):
    """Called by GET /api/summary/{id} — returns every uploaded document for this patient."""
    conn = get_db_connection()
    docs = conn.execute(
        "SELECT id AS document_id, extracted_text, structured_json FROM documents WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    conn.close()
    return [
        {"document_id": d["document_id"], "extracted_text": d["extracted_text"], "structured": json.loads(d["structured_json"])}
        for d in docs
    ]


def get_all_sessions():
    """Called by GET /api/sessions — returns every patient visit, newest first (Doctor Dashboard list)."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id AS session_id, patient_name, created_at AS started_at, status FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
