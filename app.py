import json
import os
import re
import time
from collections import defaultdict, deque

import requests
from flask import Flask, Response, jsonify, request, send_from_directory

import db

app = Flask(__name__, static_folder="static")
db.init_db()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """You are GitHelper, a friendly expert in Git and GitHub who is available 24/7.

Your job: help people fix Git/GitHub errors (push rejected, merge conflicts, authentication
failures, detached HEAD, wrong branch, large files, etc.) and walk them through any Git or
GitHub workflow step by step.

How to answer:
1. Start with one short sentence saying what the problem is and why it happens.
2. Give numbered steps. Put every command in its own fenced code block (```bash).
3. Briefly say what each command does, in plain language.
4. If you need more info to be sure, ask for the exact error text or the output of
   `git status`, `git remote -v`, or `git branch -a` - ask for only one or two things.
5. Warn clearly BEFORE any risky command (git push --force, git reset --hard, git clean -fd,
   deleting branches). Prefer safer options first (e.g. --force-with-lease, git stash).
6. For authentication errors, remember GitHub no longer accepts account passwords for Git
   over HTTPS: suggest a Personal Access Token, GitHub CLI (`gh auth login`), or SSH keys.
7. Keep answers concise and beginner-friendly. Never invent commands or flags.
8. Always reply in clear, simple English, even if the user writes in another language
   or mixes languages. Keep the commands exactly as they are.

If a question is not about Git, GitHub, or related developer workflow, politely say you only
help with Git and GitHub and invite a Git question."""

# --- very small in-memory rate limit (protects your free API quota) ---
RATE_LIMIT = 15      # messages
RATE_WINDOW = 60     # per seconds
_hits = defaultdict(deque)


def rate_limited(key):
    now = time.time()
    q = _hits[key]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


SID_RE = re.compile(r"^[a-zA-Z0-9\-]{8,64}$")


def valid_sid(sid):
    return bool(sid) and bool(SID_RE.match(sid))


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/api/history")
def history():
    sid = request.args.get("sid", "")
    if not valid_sid(sid):
        return jsonify(messages=[])
    return jsonify(messages=db.get_history(sid))


@app.post("/api/clear")
def clear():
    sid = (request.get_json(silent=True) or {}).get("session_id", "")
    if valid_sid(sid):
        db.clear_history(sid)
    return jsonify(ok=True)


@app.post("/api/chat")
def chat():
    body = request.get_json(silent=True) or {}
    sid = body.get("session_id", "")
    text = (body.get("message") or "").strip()

    if not valid_sid(sid) or not text:
        return Response("Please type a message.", status=400, mimetype="text/plain")
    if len(text) > 6000:
        return Response("Message too long (max 6000 characters).", status=400, mimetype="text/plain")
    if not GROQ_API_KEY:
        return Response("Server is missing GROQ_API_KEY.", status=500, mimetype="text/plain")
    if rate_limited(sid):
        return Response("Slow down a little - try again in a minute.", status=429, mimetype="text/plain")

    past = db.get_history(sid, limit=20)
    db.save_message(sid, "user", text)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + past + [{"role": "user", "content": text}]

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 1500,
        "stream": True,
    }
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}

    def generate():
        parts = []
        try:
            with requests.post(GROQ_URL, headers=headers, json=payload, stream=True, timeout=60) as r:
                if r.status_code != 200:
                    yield f"The AI service returned an error ({r.status_code}). Please try again shortly."
                    return
                for line in r.iter_lines():
                    if not line or not line.startswith(b"data: "):
                        continue
                    data = line[6:]
                    if data == b"[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"].get("content")
                    except (ValueError, KeyError, IndexError):
                        continue
                    if delta:
                        parts.append(delta)
                        yield delta
        except requests.RequestException:
            yield "\n\nConnection to the AI service was interrupted. Please try again."
        if parts:
            db.save_message(sid, "assistant", "".join(parts))

    return Response(generate(), mimetype="text/plain", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
