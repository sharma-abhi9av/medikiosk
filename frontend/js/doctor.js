// ============================================================================
// MediKiosk - Doctor Dashboard Logic
// ============================================================================

const API_BASE = "http://localhost:8000/api";
let currentSessionId = null;

// ----------------------------------------------------------------------------
// Fetch All Patient Sessions (GET /api/sessions)
// ----------------------------------------------------------------------------
async function fetchSessions() {
  const listElem = document.getElementById("sessionsList");

  try {
    const response = await fetch(`${API_BASE}/sessions`);
    if (!response.ok) {
      throw new Error(`Server returned HTTP ${response.status}`);
    }

    const sessions = await response.json();

    if (!Array.isArray(sessions) || sessions.length === 0) {
      listElem.innerHTML = `<div class="empty-state">No patient sessions found in database.</div>`;
      return;
    }

    listElem.innerHTML = sessions.map((s) => {
      const activeClass = s.session_id === currentSessionId ? "active" : "";
      return `
        <div class="session-item ${activeClass}" onclick="selectSession('${s.session_id}')">
          <div class="session-name">${escapeHtml(s.patient_name || "Unknown Patient")}</div>
          <div class="session-meta">
            <span>Status: ${escapeHtml(s.status || "in_progress")}</span>
            <span>${escapeHtml(s.started_at ? new Date(s.started_at).toLocaleTimeString() : "")}</span>
          </div>
          <div class="session-id">ID: ${escapeHtml(s.session_id)}</div>
        </div>
      `;
    }).join("");

  } catch (err) {
    listElem.innerHTML = `<div class="empty-state" style="color: #b91c1c;">Error loading sessions: ${escapeHtml(err.message)}</div>`;
  }
}

// ----------------------------------------------------------------------------
// Fetch Clinical Summary for Selected Session (GET /api/summary/{sessionId})
// ----------------------------------------------------------------------------
async function selectSession(sessionId) {
  currentSessionId = sessionId;
  fetchSessions(); // refresh active highlight

  const container = document.getElementById("clinicalNoteContainer");
  container.innerHTML = `<div class="empty-state">Loading summary for ${escapeHtml(sessionId)}...</div>`;

  try {
    const response = await fetch(`${API_BASE}/summary/${sessionId}`);
    if (!response.ok) {
      throw new Error(`Server returned HTTP ${response.status}`);
    }

    const data = await response.json();
    renderClinicalNote(data);

  } catch (err) {
    container.innerHTML = `<div class="empty-state" style="color: #b91c1c;">Error loading summary: ${escapeHtml(err.message)}</div>`;
  }
}

function renderClinicalNote(data) {
  const container = document.getElementById("clinicalNoteContainer");

  // Render documents if present
  let docsHtml = "<p>No documents uploaded.</p>";
  if (Array.isArray(data.documents) && data.documents.length > 0) {
    docsHtml = data.documents.map((d) => `
      <div class="doc-item">
        <strong>Extracted Prescription / Lab Text:</strong>
        <pre class="doc-text">${escapeHtml(d.extracted_text || "")}</pre>
      </div>
    `).join("");
  }

  container.innerHTML = `
    <div class="clinical-note">
      <div class="note-header">
        <h2>Clinical Intake Note</h2>
        <div class="note-meta">Session ID: <code>${escapeHtml(data.session_id)}</code></div>
      </div>

      <div class="note-section">
        <h3>Chief Complaint</h3>
        <p>${escapeHtml(data.chief_complaint || "Not recorded")}</p>
      </div>

      <div class="note-section">
        <h3>History of Present Illness (HPI)</h3>
        <p>${escapeHtml(data.hpi || "Not recorded")}</p>
      </div>

      <div class="note-section">
        <h3>Past Medical History</h3>
        <p>${escapeHtml(data.past_history || "None reported")}</p>
      </div>

      <div class="note-section">
        <h3>Drug & Allergy History</h3>
        <p>${escapeHtml(data.drug_allergy_history || "None reported")}</p>
      </div>

      <div class="note-section">
        <h3>Uploaded Documents & OCR</h3>
        ${docsHtml}
      </div>
    </div>
  `;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

window.addEventListener("DOMContentLoaded", () => {
  fetchSessions();

  const refreshBtn = document.getElementById("refreshSessionsBtn");
  if (refreshBtn) {
    refreshBtn.onclick = fetchSessions;
  }
});
