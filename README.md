# Hackathon Repository Evaluator

A web-based tool for technical judging of hackathon code submissions. Judges can analyze public GitHub repos for code quality, completeness, efficiency, error handling, version control, technology use, and more. Participants can view full feedback and scores for their own or other teams' submissions.

---

## Features
- **Judge/Admin app** (`webapp.py`):
  - Submit a repo URL and (optionally) a problem statement
  - Runs a technical analysis using an LLM (Groq)
  - Scores: code quality, completeness, efficiency, error handling, version control, technology use
  - Narrative feedback: summary, technical overview, what's missing, how to make it better, etc.
  - Saves every analysis to a local SQLite DB
  - Clean UI, recent analyses list, and detail pages
- **Participant app** (`participant_app.py`):
  - Read-only view of all analyses and full feedback
  - Same detail view as admin (all scores, justifications, summary, etc.)

## Quickstart

1. **Clone and install dependencies**
   ```bash
   git clone <this-repo-url>
   cd <repo-dir>
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Set up your Groq API key**
   - Copy `.env.example` to `.env` and paste your key:
     ```bash
     cp .env.example .env
     # Edit .env and set GROQ_API_KEY=sk-xxxYOURKEYxxx
     ```

3. **Run the judge/admin app**
   ```bash
   python webapp.py
   # Visit http://127.0.0.1:5000/
   ```
   - Submit a repo URL, wait for LLM analysis, see/save results

4. **Run the participant app** (optional, can be on a different port/server)
   ```bash
   python participant_app.py
   # Visit http://127.0.0.1:5001/
   ```
   - Anyone can browse all analyses and see full feedback

## File Structure

- `webapp.py` — Admin/judge UI (submit, analyze, review)
- `participant_app.py` — Read-only participant UI
- `git_ingest.py` — Repo ingestion utility
- `analysis.db` — SQLite DB (auto-created)
- `templates/` — Jinja2 HTML templates
- `requirements.txt` — Python dependencies
- `.env.example` — Example env file for API secrets
- `.gitignore` — Ignore secrets, DB, venv, etc.

## Environment Variables

All secrets and API keys must be set in a `.env` file:

```
GROQ_API_KEY=sk-xxxYOURKEYxxx
```

**Never commit your real `.env` or API keys!**

## Security
- `.env` and `analysis.db` are gitignored by default.
- Do not use the built-in Flask server for production.

## License
MIT
