"""
Central configuration – edit this file to tune behaviour.
No logic lives here; only constants.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Gmail IMAP + OAuth2
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials", "credentials.json")
TOKEN_FILE       = os.path.join(BASE_DIR, "credentials", "token.json")
GMAIL_SCOPES     = ["https://www.googleapis.com/auth/gmail.readonly"]
IMAP_HOST        = "imap.gmail.com"
IMAP_PORT        = 993

# Local LLM (Ollama)
OLLAMA_BASE_URL          = "http://localhost:11434"
OLLAMA_MODEL             = "llama3.2"
OLLAMA_TIMEOUT_S         = 30
LLM_ESCALATION_THRESHOLD = 0.70
LLM_ENABLED              = True

# Logging
LOG_FILE  = os.path.join(BASE_DIR, "logs", "assistant.log")
LOG_LEVEL = "INFO"

# Notifications
NOTIFICATION_APP_NAME     = "Deadline Assistant"
NOTIFICATION_TIMEOUT_SECS = 12
SNOOZE_HOURS              = 24

# Action-type labels
ACTION_LABELS = {
    "payment_due":          "Payment Due",
    "follow_up_deadline":   "Follow-Up Deadline",
    "reply_deadline":       "Reply Deadline",
    "submission_deadline":  "Submission Deadline",
    "cancellation_notice":  "Cancellation / Contract Notice",
    "no_action":            "No Action Required",
    "unknown":              "Deadline",
}

# Deadline / reminder timing
REMINDER_DAYS_BEFORE   = 1
DEFAULT_DEADLINE_HOUR  = 17   # 5 PM
DEFAULT_REMINDER_HOUR  = 9    # 9 AM