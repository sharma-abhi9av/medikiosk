import sqlite3
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
    This is exactly what the AI Conversationalist's conversation_history input looks like,
    and what the Summary function reads to rebuild the conversation."""
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
