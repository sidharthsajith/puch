"""Flask-based web interface for the hackathon repository evaluator.

Features
--------
1. Accepts a public GitHub repository URL and optional problem statement.
2. Clones the repo (shallow) and builds a digest via ``git_ingest.ingest_repo``.
3. Sends the digest to Groq LLM to score multiple criteria and compute overall score.
4. Persists each evaluation to a lightweight SQLite DB (via ``sqlite3``) so the user
   can review past analyses.
5. Basic HTML interface powered by Jinja2 templates stored in ``templates/``.

ENVIRONMENT VARIABLES
---------------------
GROQ_API_KEY – Required to reach Groq. Obtain from https://console.groq.com/

Run locally with:
$ python webapp.py
Then open http://127.0.0.1:5000/ in a browser.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict

from flask import Flask, redirect, render_template, request, url_for
from dotenv import load_dotenv

from git_ingest import ingest_repo

# ---------------------------------------------------------------------------
# Configuration & helpers
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "analysis.db"


def _init_db() -> None:
    """Create the SQLite table on first run."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                repo_url TEXT NOT NULL,
                problem_statement TEXT,
                result_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


# ---------------------------------------------------------------------------
# LLM interaction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "As an impartial technical evaluator for a 12-hour hackathon, analyze the provided GitHub "
    "repository. Your assessment must be strictly objective and focus solely on the technical "
    "merits of the codebase, considering the limited development time. Avoid any bias toward or "
    "against particular technologies, programming languages, frameworks, authors, or organizations. "
    "For each evaluation criterion, provide a score from 1 to 100 (with 100 being perfect) and "
    "include a detailed justification for each score. Respond ONLY with JSON using the following "
    "exact schema: {\n  \"repository_url\": \"string\",\n  \"problem_statement\": \"string\",\n  "
    "\"scores\": {\n    \"code_quality_readability\": {\"score\": 0, \"justification\": \"string\"},\n    "
    "\"functionality_completeness\": {\"score\": 0, \"justification\": \"string\"},\n    "
    "\"efficiency_performance\": {\"score\": 0, \"justification\": \"string\"},\n    "
    "\"error_handling_robustness\": {\"score\": 0, \"justification\": \"string\"},\n    "
    "\"version_control_practices\": {\"score\": 0, \"justification\": \"string\"},\n    "
    "\"technology_utilization\": {\"score\": 0, \"justification\": \"string\"}\n  },\n  "
    "\"overall_score\": 0,\n  \"technical_overview\": \"string\",\n  \"description_of_judgement\": \"string\",\n  "
    "\"conclusion\": \"string\",\n  \"whats_missing\": \"string\",\n  \"what_to_include\": \"string\",\n  "
    "\"how_to_make_it_better\": \"string\",\n  \"why_a_winning_product\": \"string\",\n  "
    "\"why_a_losing_product\": \"string\",\n  \"summary_assessment\": \"string\"\n}. "
    "Calculate overall_score as the weighted average using weights: CQ 25%, FC 30%, EP 15%, EH 10%, VC 10%, TU 10%."
)


try:
    # Optional at import-time; will fail unit tests if missing but web route handles
    from groq import Groq  # type: ignore
except ModuleNotFoundError:
    Groq = None  # type: ignore  # noqa: N816


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)
_init_db()


@app.template_filter("datetimeformat")
def _dt_filter(value: int) -> str:  # pragma: no cover
    """Convert epoch seconds to human-readable date."""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(value))


@app.route("/")
def index():  # type: ignore
    """Home page with submission form and list of past analyses."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, timestamp, repo_url, overall_score FROM ("  # type: ignore
            "  SELECT id, timestamp, repo_url, json_extract(result_json, '$.overall_score') AS overall_score "
            "  FROM analysis ORDER BY id DESC LIMIT 20"  # most recent 20
            ")"
        ).fetchall()
    analyses = [dict(row) for row in rows]
    return render_template("index.html", analyses=analyses)


@app.route("/analyze", methods=["POST"])
def analyze():  # type: ignore
    load_dotenv()
    repo_url = request.form["repo_url"].strip()
    problem_statement = request.form.get("problem_statement", "").strip()
    if not repo_url:
        return "Repository URL is required", 400

    # Build repository digest (may take a few seconds)
    summary, tree, content = ingest_repo(repo_url)
    code_context = "\n\n".join([summary, tree, content])

    # Prepare LLM prompt
    user_prompt = (
        "Analyze the repository with the following details.\n"
        f"Repository URL: {repo_url}\n"
        f"Problem Statement: {problem_statement or '(none)'}\n\n"
        "Repository data:\n" + code_context
    )

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key or Groq is None:
        # Graceful degradation – return a dummy response
        result: Dict[str, Any] = {
            "repository_url": repo_url,
            "problem_statement": problem_statement,
            "scores": {
                "code_quality_readability": {"score": 50, "justification": "N/A (offline)"},
                "functionality_completeness": {"score": 50, "justification": "N/A (offline)"},
                "efficiency_performance": {"score": 50, "justification": "N/A (offline)"},
                "error_handling_robustness": {"score": 50, "justification": "N/A (offline)"},
                "version_control_practices": {"score": 50, "justification": "N/A (offline)"},
                "technology_utilization": {"score": 50, "justification": "N/A (offline)"},
            },
            "overall_score": 50,
            "summary_assessment": "Groq API key not configured; displaying placeholder data.",
        }
    else:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)  # type: ignore[arg-type]

    # Persist to DB
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO analysis (timestamp, repo_url, problem_statement, result_json) VALUES (?, ?, ?, ?)",
            (int(time.time()), repo_url, problem_statement, json.dumps(result)),
        )
        conn.commit()
        analysis_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return redirect(url_for("view_analysis", analysis_id=analysis_id))


@app.route("/analysis/<int:analysis_id>")
def view_analysis(analysis_id: int):  # type: ignore
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT repo_url, problem_statement, result_json FROM analysis WHERE id = ?",
            (analysis_id,),
        ).fetchone()
    if not row:
        return "Analysis not found", 404

    result = json.loads(row[2])
    return render_template(
        "analysis.html",
        repo_url=row[0],
        problem_statement=row[1],
        result=result,
    )


if __name__ == "__main__":
    app.run(debug=True)
