import os
import uuid
import socket

from fastapi import FastAPI, UploadFile, Form, File
from fastapi.responses import HTMLResponse
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


def get_local_ip():
    """Automatically detects this machine's actual LAN IP address — no
    hardcoding, works on whatever network the server is currently running on.

    Trick: open a UDP socket and 'connect' to a public IP (8.8.8.8). This
    doesn't actually send any data anywhere — it just asks the operating
    system which local network interface/IP it WOULD use to reach that
    address, which is exactly the IP other devices on the same network can
    use to reach this machine. Falls back to localhost if there's no network
    connection at all (e.g. testing fully offline).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


@app.get("/api/server-info")
def server_info():
    return {"local_ip": get_local_ip(), "port": 8000}


@app.post("/api/session/start")
def start_session(data: dict):
    session_id = str(uuid.uuid4())
    started_at = now()

    save_new_session(session_id, data.get("patient_name"), data.get("language"), data.get("abha_id"), started_at)

    return {"session_id": session_id, "patient_name": data.get("patient_name"), "started_at": started_at}


@app.post("/api/consent")
def consent(data: dict):
    session_id = data["session_id"]
    consent_given = data.get("consent_given", False)
    logged_at = now()

    log_session_consent(session_id, consent_given, logged_at)

    with open("consent_audit.log", "a") as f:
        f.write(f"[{logged_at}] session {session_id}: consent_given={consent_given}\n")

    return {"status": "ok", "logged_at": logged_at}


@app.post("/api/converse")
def converse(data: dict):
    session_id = data["session_id"]
    patient_answer = data["patient_answer"]

    history = get_conversation_history(session_id)
    current_stage = history[-1]["stage"] if history else "chief_complaint"

    from ai_engine import get_next_question
    result = get_next_question(history, patient_answer, current_stage)

    save_message(session_id, "patient", patient_answer, current_stage)
    save_message(session_id, "ai", result["ai_question"], result["stage"])

    if result.get("is_complete"):
        update_session_status(session_id, "awaiting_documents")

    return result


# ---------------------------------------------------------------------------
# EXTRA: GET /mobile-upload/{session_id} — a tiny page a patient's own phone
# opens after scanning a QR code shown on the kiosk. It has one upload button
# that calls the SAME POST /api/upload-document endpoint below, with the
# session_id already baked into the page — no separate upload logic needed.
# NOTE: only reachable if the phone is on the same WiFi network as this
# server (see the note Mikey has for the team on this).
# ---------------------------------------------------------------------------
@app.get("/mobile-upload/{session_id}", response_class=HTMLResponse)
def mobile_upload_page(session_id: str):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Upload Prescription — MediKiosk</title>
        <style>
            body {{
                font-family: sans-serif;
                background: #0B4F4A;
                color: white;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
                padding: 20px;
                text-align: center;
                box-sizing: border-box;
            }}
            h2 {{ margin-bottom: 8px; }}
            p {{ opacity: 0.85; margin-bottom: 24px; }}
            input[type="file"] {{
                margin-bottom: 20px;
                color: white;
            }}
            button {{
                background: #14A098;
                color: white;
                border: none;
                padding: 14px 28px;
                font-size: 16px;
                border-radius: 8px;
                cursor: pointer;
            }}
            button:disabled {{ opacity: 0.5; }}
            #status {{ margin-top: 20px; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h2>Upload Your Prescription</h2>
        <p>Select a photo or PDF of your prescription from your phone.</p>
        <input type="file" id="fileInput" accept="image/*,.pdf">
        <button id="uploadBtn" onclick="uploadFile()">Upload</button>
        <div id="status"></div>

        <script>
            const sessionId = "{session_id}";

            async function uploadFile() {{
                const fileInput = document.getElementById("fileInput");
                const status = document.getElementById("status");
                const btn = document.getElementById("uploadBtn");

                if (!fileInput.files.length) {{
                    status.textContent = "Please choose a file first.";
                    return;
                }}

                btn.disabled = true;
                status.textContent = "Uploading...";

                const formData = new FormData();
                formData.append("session_id", sessionId);
                formData.append("file", fileInput.files[0]);

                try {{
                    const response = await fetch("/api/upload-document", {{
                        method: "POST",
                        body: formData,
                    }});
                    if (response.ok) {{
                        status.textContent = "Uploaded! You can return to the kiosk now.";
                    }} else {{
                        status.textContent = "Upload failed — please try again.";
                        btn.disabled = false;
                    }}
                }} catch (err) {{
                    status.textContent = "Network error — check your connection and try again.";
                    btn.disabled = false;
                }}
            }}
        </script>
    </body>
    </html>
    """


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
