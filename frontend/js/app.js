// ============================================================================
// MediKiosk - Patient Kiosk Frontend
// ============================================================================

// Declared at the very top of app.js outside every function
let sessionId = null;
let selectedLang = "en";

// Backend API URL (Mikey's server)
const API_BASE = "http://localhost:8000/api";

// A fetch resolves even for HTTP 4xx/5xx responses. Check the status before
// advancing a patient to the next screen, otherwise a failed request leaves
// the kiosk with an invalid or missing session ID.
async function ensureApiSuccess(response) {
  if (response.ok) return;

  let message = `Server returned HTTP ${response.status}`;
  try {
    const error = await response.json();
    message = error.detail || error.message || message;
  } catch (_) {
    // Keep the HTTP status message when the server did not return JSON.
  }
  throw new Error(message);
}

// Bilingual text for UI static text (English and Hindi)
const UI_TEXT = {
  en: {
    titleIdentify: "Patient Identification",
    descIdentify: "Please enter your details to begin your consultation intake.",
    labelPatientName: "Full Name",
    placeholderPatientName: "Enter your name",
    labelAbhaId: "ABHA ID",
    continueBtn: "Continue",

    titleConsent: "Patient Consent",
    descConsent: "Please review and provide your consent to continue.",
    consentPoints: `
      <p>By proceeding, you consent to sharing your reported symptoms and past medical history with your attending physician.</p>
      <p>Your data is processed securely for this consultation intake in compliance with DPDP and ABDM standards.</p>
      <p>The AI assistant assists in organizing your medical history; the final diagnosis and prescription will be made directly by your doctor.</p>
    `,
    consentCheckboxLabel: "I agree to the collection and clinical processing of my health intake for this visit.",

    inputPlaceholder: "Tap mic to speak, or type your answer here...",
    sendBtn: "Send",

    titleUpload: "Document Upload",
    descUpload: "Upload a photo of your previous prescription or medical report (optional).",
    uploadPromptText: "Tap to select photo or scan prescription",
    ocrHeader: "Extracted Text:",
    ocrConfirmPrompt: "Is this correct?",
    ocrConfirmBtn: "Confirm & Continue",
    skipBtn: "Skip",

    titleReview: "Review",
    descReview: "Please review your recorded intake before submitting to your doctor.",
    submitReviewBtn: "Submit",

    titleCompleted: "Intake Submitted",
    descCompleted: "Your clinical summary has been sent directly to the doctor's screen. Please wait to be called.",
    startNewVisitBtn: "Start New Patient Visit"
  },
  hi: {
    titleIdentify: "मरीज़ पहचान",
    descIdentify: "परामर्श इनटेक शुरू करने के लिए कृपया अपना विवरण दर्ज करें।",
    labelPatientName: "पूरा नाम",
    placeholderPatientName: "अपना नाम दर्ज करें",
    labelAbhaId: "आभा आईडी",
    continueBtn: "आगे बढ़ें",

    titleConsent: "मरीज़ सहमति",
    descConsent: "आगे बढ़ने के लिए कृपया नियम पढ़ें और अपनी सहमति दें।",
    consentPoints: `
      <p>आगे बढ़कर, आप अपने लक्षणों और पुराने मेडिकल इतिहास को डॉक्टर के साथ साझा करने की सहमति देते हैं।</p>
      <p>आपकी जानकारी डीपीडीपी और एबीडीएम मानकों के तहत सुरक्षित रूप से संसाधित की जाती है।</p>
      <p>एआई सहायक केवल आपकी जानकारी व्यवस्थित करता है; अंतिम उपचार और दवा का निर्णय आपके डॉक्टर द्वारा लिया जाएगा।</p>
    `,
    consentCheckboxLabel: "मैं इस परामर्श के लिए अपनी स्वास्थ्य जानकारी एकत्र करने और संसाधित करने की सहमति देता/देती हूँ।",

    inputPlaceholder: "बोलने के लिए माइक दबाएं या यहाँ टाइप करें...",
    sendBtn: "भेजें",

    titleUpload: "दस्तावेज़ अपलोड",
    descUpload: "पुराने पर्चे या रिपोर्ट की फोटो अपलोड करें (वैकल्पिक)।",
    uploadPromptText: "फोटो चुनने या पर्चा स्कैन करने के लिए टैप करें",
    ocrHeader: "पहचाना गया टेक्स्ट:",
    ocrConfirmPrompt: "क्या यह सही है?",
    ocrConfirmBtn: "पुष्टि करें और आगे बढ़ें",
    skipBtn: "छोड़ें (Skip)",

    titleReview: "समीक्षा",
    descReview: "डॉक्टर को भेजने से पहले अपने दर्ज विवरण की समीक्षा करें।",
    submitReviewBtn: "जमा करें",

    titleCompleted: "इनटेक जमा हो गया",
    descCompleted: "आपका क्लिनिकल सारांश सीधे डॉक्टर की स्क्रीन पर भेज दिया गया है। कृपया प्रतीक्षा करें।",
    startNewVisitBtn: "नए मरीज़ का इनटेक शुरू करें"
  }
};

// ----------------------------------------------------------------------------
// Screen Switcher
// ----------------------------------------------------------------------------
function showScreen(screenId) {
  document.querySelectorAll(".kiosk-screen").forEach((screen) => {
    screen.classList.remove("active");
  });
  const target = document.getElementById(screenId);
  if (target) {
    target.classList.add("active");
  }

  // When opening consent screen, always enforce clean unchecked state
  if (screenId === "screen-consent") {
    const consentBox = document.getElementById("consentCheckbox");
    const consentBtn = document.getElementById("consentContinueBtn");
    if (consentBox) consentBox.checked = false;
    if (consentBtn) consentBtn.disabled = true;
  }
}

// ----------------------------------------------------------------------------
// Language Selector (Two buttons: English / हिंदी)
// ----------------------------------------------------------------------------
function setLanguage(lang) {
  selectedLang = lang;

  const btnEn = document.getElementById("langBtnEn");
  const btnHi = document.getElementById("langBtnHi");
  if (btnEn && btnHi) {
    btnEn.classList.toggle("active", lang === "en");
    btnHi.classList.toggle("active", lang === "hi");
  }

  const t = UI_TEXT[lang] || UI_TEXT.en;

  // Update text content
  const setTxt = (id, txt) => {
    const el = document.getElementById(id);
    if (el) el.innerText = txt;
  };

  setTxt("titleIdentify", t.titleIdentify);
  setTxt("descIdentify", t.descIdentify);
  setTxt("labelPatientName", t.labelPatientName);
  setTxt("labelAbhaId", t.labelAbhaId);
  setTxt("identifyContinueBtn", t.continueBtn);

  setTxt("titleConsent", t.titleConsent);
  setTxt("descConsent", t.descConsent);
  const consentBox = document.getElementById("consentTextContent");
  if (consentBox) consentBox.innerHTML = t.consentPoints;
  setTxt("consentCheckboxLabel", t.consentCheckboxLabel);
  setTxt("consentContinueBtn", t.continueBtn);

  const inputElem = document.getElementById("patientNameInput");
  if (inputElem) inputElem.placeholder = t.placeholderPatientName;

  const answerInput = document.getElementById("patientAnswerInput");
  if (answerInput) answerInput.placeholder = t.inputPlaceholder;
  setTxt("sendMessageBtn", t.sendBtn);

  setTxt("titleUpload", t.titleUpload);
  setTxt("descUpload", t.descUpload);
  setTxt("uploadPromptText", t.uploadPromptText);
  setTxt("ocrHeader", t.ocrHeader);
  setTxt("ocrConfirmPrompt", t.ocrConfirmPrompt);
  setTxt("ocrConfirmBtn", t.ocrConfirmBtn);
  setTxt("skipUploadBtn", t.skipBtn);

  setTxt("titleReview", t.titleReview);
  setTxt("descReview", t.descReview);
  setTxt("submitReviewBtn", t.submitReviewBtn);

  setTxt("titleCompleted", t.titleCompleted);
  setTxt("descCompleted", t.descCompleted);
  setTxt("startNewVisitBtn", t.startNewVisitBtn);

  // Update speech recognition language
  if (recognition) {
    recognition.lang = selectedLang === "hi" ? "hi-IN" : "en-IN";
  }
}

let isRecording = false;

function setMicButtonState(recording) {
  isRecording = recording;
  const micButton = document.getElementById("micButton");
  if (!micButton) return;
  if (recording) {
    micButton.innerText = "✕";
    micButton.classList.add("recording");
    micButton.title = "Tap to abort recording";
  } else {
    micButton.innerText = "🎤";
    micButton.classList.remove("recording");
    micButton.title = "Tap to speak";
  }
}

function toggleMicRecording() {
  if (isRecording) {
    // Currently recording -> abort
    if (recognition) {
      try {
        recognition.abort();
      } catch (e) {
        console.warn("Recognition abort:", e);
      }
    }
    setMicButtonState(false);
  } else {
    // Not recording -> start recording
    if (!recognition) {
      alert("Speech recognition is not supported in this browser. Please type your answer.");
      return;
    }
    try {
      recognition.lang = selectedLang === "hi" ? "hi-IN" : "en-IN";
      recognition.start();
      setMicButtonState(true);
    } catch (err) {
      console.warn("Recognition start error:", err);
      setMicButtonState(false);
    }
  }
}

// ----------------------------------------------------------------------------
// Voice Input (SpeechRecognition - Runs entirely in browser)
// ----------------------------------------------------------------------------
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.lang = selectedLang === "hi" ? "hi-IN" : "en-IN";
  recognition.continuous = false;
  recognition.interimResults = false;

  recognition.onstart = () => {
    setMicButtonState(true);
  };

  recognition.onresult = (event) => {
    setMicButtonState(false);
    const spokenText = event.results[0][0].transcript;
    sendAnswerToBackend(spokenText);
  };

  recognition.onerror = (event) => {
    console.warn("Speech recognition error:", event.error);
    setMicButtonState(false);
  };

  recognition.onend = () => {
    setMicButtonState(false);
  };
}

// ----------------------------------------------------------------------------
// 1. Patient Identify (POST /api/session/start)
// ----------------------------------------------------------------------------
async function handlePatientIdentify() {
  const patient_name = document.getElementById("patientNameInput").value.trim();
  const abha_id = document.getElementById("abhaIdInput").value.trim();

  if (!patient_name) {
    alert(selectedLang === "hi" ? "कृपया अपना नाम दर्ज करें" : "Please enter your name");
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/session/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patient_name, language: selectedLang, abha_id })
    });

    await ensureApiSuccess(response);
    const data = await response.json();
    if (!data.session_id) {
      throw new Error("The server did not return a session ID.");
    }
    sessionId = data.session_id; // Save globally
    showScreen("screen-consent");
  } catch (err) {
    alert("Error starting session: " + err.message);
  }
}

// ----------------------------------------------------------------------------
// 2. Consent (POST /api/consent)
// ----------------------------------------------------------------------------
async function handlePatientConsent() {
  const consentBox = document.getElementById("consentCheckbox");
  if (!consentBox || !consentBox.checked) return;

  try {
    const response = await fetch(`${API_BASE}/consent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, consent_given: true })
    });

    await ensureApiSuccess(response);
    const data = await response.json();
    if (data.status === "ok") {
      showScreen("screen-conversation");
      // Initial conversational prompt for patient
      appendMessage("ai", selectedLang === "hi" 
        ? "नमस्ते! कृपया बताएं कि आज आपको क्या स्वास्थ्य समस्या हो रही है?"
        : "Hello! Please tell us what symptoms you are experiencing today."
      );
    }
  } catch (err) {
    alert("Error recording consent: " + err.message);
  }
}

// ----------------------------------------------------------------------------
// 3. Conversation (POST /api/converse)
// ----------------------------------------------------------------------------
async function sendAnswerToBackend(theirAnswerText) {
  const text = (theirAnswerText || "").trim();
  if (!text) return;

  // Clear input field
  const inputElem = document.getElementById("patientAnswerInput");
  if (inputElem) inputElem.value = "";

  // Show patient bubble
  appendMessage("patient", text);

  try {
    const response = await fetch(`${API_BASE}/converse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, patient_answer: text })
    });

    await ensureApiSuccess(response);
    const data = await response.json();
    // data = { ai_question, stage, is_complete }

    if (data.ai_question) {
      appendMessage("ai", data.ai_question);
    }

    // Check is_complete specifically:
    // If false: stay on Screen 3 (conversation), wait for patient to speak/type again.
    // If true: chat is officially complete, disable input and proceed to upload.
    if (data.is_complete === true || data.is_complete === "true") {
      const inputElem = document.getElementById("patientAnswerInput");
      const sendBtn = document.getElementById("sendMessageBtn");
      const micBtn = document.getElementById("micButton");
      if (inputElem) inputElem.disabled = true;
      if (sendBtn) sendBtn.disabled = true;
      if (micBtn) micBtn.disabled = true;

      setTimeout(() => {
        showScreen("screen-upload");
      }, 1500);
    }
  } catch (err) {
    appendMessage("ai", "Error reaching backend: " + err.message);
  }
}

function appendMessage(sender, text) {
  const chatMessages = document.getElementById("chatMessages");
  if (!chatMessages) return;

  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${sender}`;
  bubble.innerText = text;

  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ----------------------------------------------------------------------------
// 4. Document Upload (POST /api/upload-document)
// ----------------------------------------------------------------------------
async function handleDocumentUpload(file) {
  if (!file) return;

  if (!sessionId) {
    alert(selectedLang === "hi" 
      ? "सत्र नहीं मिला। कृपया शुरुआत से प्रारंभ करें।" 
      : "Session not found. Please start from the beginning.");
    showScreen("screen-identify");
    return;
  }

  const uploadPrompt = document.getElementById("uploadPromptText");
  const originalPromptText = uploadPrompt ? uploadPrompt.innerText : "";
  if (uploadPrompt) {
    uploadPrompt.innerText = selectedLang === "hi"
      ? "दस्तावेज़ स्कैन हो रहा है... कृपया प्रतीक्षा करें"
      : "Scanning document... Please wait";
  }

  // Use FormData per instruction
  const formData = new FormData();
  formData.append("session_id", sessionId);
  formData.append("file", file);

  try {
    const response = await fetch(`${API_BASE}/upload-document`, {
      method: "POST",
      body: formData
    });

    await ensureApiSuccess(response);
    const data = await response.json();
    // data = { document_id, extracted_text, structured: { medicines: [...], date: "..." } }

    const ocrBox = document.getElementById("ocrResultBox");
    const extractedTextElem = document.getElementById("extractedTextDisplay");
    if (ocrBox && extractedTextElem) {
      extractedTextElem.innerText = data.extracted_text || "No text extracted.";
      ocrBox.style.display = "block";
    }
  } catch (err) {
    alert("Error uploading document: " + err.message);
  } finally {
    if (uploadPrompt) {
      uploadPrompt.innerText = originalPromptText || (selectedLang === "hi"
        ? "फोटो चुनने या पर्चा स्कैन करने के लिए टैप करें"
        : "Tap to select photo or scan prescription");
    }
  }
}

// ----------------------------------------------------------------------------
// 5. Patient Review (GET /api/summary/{sessionId})
// ----------------------------------------------------------------------------
async function loadSummary() {
  try {
    const response = await fetch(`${API_BASE}/summary/${sessionId}`);
    await ensureApiSuccess(response);
    const data = await response.json();

    const sentenceElem = document.getElementById("summarySentence");
    const detailsElem = document.getElementById("summaryDetails");

    const complaint = data.chief_complaint || "None recorded";
    if (sentenceElem) {
      sentenceElem.innerText = selectedLang === "hi"
        ? `हमने दर्ज किया है: ${complaint}`
        : `We've recorded: ${complaint}`;
    }

    if (detailsElem) {
      detailsElem.innerHTML = `
        <p><strong>HPI:</strong> ${escapeHtml(data.hpi || "N/A")}</p>
        <p><strong>Past History:</strong> ${escapeHtml(data.past_history || "N/A")}</p>
        <p><strong>Allergies / Medications:</strong> ${escapeHtml(data.drug_allergy_history || "N/A")}</p>
      `;
    }
  } catch (err) {
    const sentenceElem = document.getElementById("summarySentence");
    if (sentenceElem) {
      sentenceElem.innerText = "Error loading summary: " + err.message;
    }
  }
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

function resetVisit() {
  if (isRecording) {
    toggleMicRecording();
  }
  sessionId = null;
  document.getElementById("patientNameInput").value = "";
  document.getElementById("abhaIdInput").value = "14-XXXX-XXXX-XXXX";
  const answerInput = document.getElementById("patientAnswerInput");
  const sendBtn = document.getElementById("sendMessageBtn");
  const micBtn = document.getElementById("micButton");
  if (answerInput) {
    answerInput.value = "";
    answerInput.disabled = false;
  }
  if (sendBtn) sendBtn.disabled = false;
  if (micBtn) micBtn.disabled = false;

  document.getElementById("consentCheckbox").checked = false;
  document.getElementById("consentContinueBtn").disabled = true;
  document.getElementById("chatMessages").innerHTML = "";
  document.getElementById("ocrResultBox").style.display = "none";
  const docInput = document.getElementById("docFileInput");
  if (docInput) docInput.value = "";
  showScreen("screen-identify");
}

// ----------------------------------------------------------------------------
// DOM Initialization
// ----------------------------------------------------------------------------
window.addEventListener("DOMContentLoaded", () => {
  // Request fullscreen once on page load (or on first interaction if blocked by browser)
  try {
    if (document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  } catch (e) {}

  document.addEventListener("click", function firstClickFullscreen() {
    if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(() => {});
    }
    document.removeEventListener("click", firstClickFullscreen);
  }, { once: true });

  // Language buttons
  const btnEn = document.getElementById("langBtnEn");
  const btnHi = document.getElementById("langBtnHi");
  if (btnEn) btnEn.onclick = () => setLanguage("en");
  if (btnHi) btnHi.onclick = () => setLanguage("hi");

  // Screen 1: Identify Continue button
  const identifyBtn = document.getElementById("identifyContinueBtn");
  if (identifyBtn) identifyBtn.onclick = handlePatientIdentify;

  // Screen 2: Consent Checkbox & Continue button
  const consentBox = document.getElementById("consentCheckbox");
  const consentBtn = document.getElementById("consentContinueBtn");
  if (consentBox && consentBtn) {
    consentBox.checked = false;
    consentBtn.disabled = true;

    const syncConsentState = () => {
      consentBtn.disabled = !consentBox.checked;
    };
    consentBox.addEventListener("change", syncConsentState);
    consentBox.addEventListener("input", syncConsentState);
    consentBtn.onclick = handlePatientConsent;
  }

  // Screen 3: Conversation Mic (toggles between 🎤 and ✕) & Send buttons
  const micButton = document.getElementById("micButton");
  if (micButton) {
    micButton.onclick = toggleMicRecording;
  }

  const sendBtn = document.getElementById("sendMessageBtn");
  const answerInput = document.getElementById("patientAnswerInput");
  if (sendBtn && answerInput) {
    sendBtn.onclick = () => sendAnswerToBackend(answerInput.value);
    answerInput.onkeydown = (e) => {
      if (e.key === "Enter") {
        sendAnswerToBackend(answerInput.value);
      }
    };
  }

  // Screen 4: Document Upload
  const uploadZone = document.getElementById("uploadZone");
  const docFileInput = document.getElementById("docFileInput");
  const skipUploadBtn = document.getElementById("skipUploadBtn");
  const ocrConfirmBtn = document.getElementById("ocrConfirmBtn");

  if (uploadZone && docFileInput) {
    uploadZone.onclick = () => docFileInput.click();
    docFileInput.onchange = (e) => {
      if (e.target.files && e.target.files[0]) {
        handleDocumentUpload(e.target.files[0]);
      }
    };
  }

  if (skipUploadBtn) {
    skipUploadBtn.onclick = () => {
      // Tap Skip: make no backend call, just move on
      showScreen("screen-review");
      loadSummary();
    };
  }

  if (ocrConfirmBtn) {
    ocrConfirmBtn.onclick = () => {
      showScreen("screen-review");
      loadSummary();
    };
  }

  // Screen 5: Submit Review
  const submitReviewBtn = document.getElementById("submitReviewBtn");
  if (submitReviewBtn) {
    submitReviewBtn.onclick = () => {
      showScreen("screen-completed");
    };
  }

  // Screen 5b: Start New Visit
  const startNewVisitBtn = document.getElementById("startNewVisitBtn");
  if (startNewVisitBtn) {
    startNewVisitBtn.onclick = resetVisit;
  }

  // Set default language and initial screen
  setLanguage("en");
  showScreen("screen-identify");
});
