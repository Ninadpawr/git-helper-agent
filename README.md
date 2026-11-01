# GitHelper – Git & GitHub help agent

Flask + Groq (free, fast LLM) + SQLite/Postgres history. Streams answers, remembers chats per browser.

## Run locally
```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
export GROQ_API_KEY=your_key                          # Windows: set GROQ_API_KEY=your_key
python app.py                                         # open http://localhost:5000
```

## Deploy free (Render + Neon + UptimeRobot)
See the step-by-step guide in the chat answer. Build command: `pip install -r requirements.txt`,
start command: `gunicorn app:app --workers 1 --threads 8 --timeout 120`.
Env vars: `GROQ_API_KEY`, `DATABASE_URL` (Neon), `PYTHON_VERSION=3.11.9`.
Health check path: `/health`.
