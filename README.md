# Gmail-Deadline-Assistant

A fully local email assistant that reads Gmail messages on-device, detects deadlines (payment, follow-up, reply, submission, contract), resolves explicit/relative dates, sets reminders 1 day prior, and shows desktop notifications, without sending data to external AI or SaaS services.

## Structure of the Project

gmail-deadline-agent/
│
├── config/
│ ├── **init**.py ← empty, makes it a package
│ └── settings.py ← ALL constants in one place
│
├── src/
│ └── **init**.py ← empty
│
├── tests/
│ └── **init**.py ← empty
│
├── credentials/
│ └── .gitkeep ← folder exists, nothing committed
│
├── data/
│ └── .gitkeep
│
├── logs/
│ └── .gitkeep
│
├── .github/
│ └── workflows/
│ └── ci.yml ← CI from day 1 (catches mistakes early)
│
├── .gitignore ← credentials/, data/, logs/, .venv/
├── requirements.txt ← pin ALL versions today
└── README.md ← project purpose, one paragraph
