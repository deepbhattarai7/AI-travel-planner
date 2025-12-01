# app.py — Render-ready entrypoint (no hardcoded keys)
import os
import logging
import traceback
from flask import Flask, render_template, request
from dotenv import load_dotenv

# load .env locally (does nothing on Render)
load_dotenv()

# import orchestration helpers
from crew.crew_runner import run_travel_crew, check_required_env

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("travel-app")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")  # set SECRET_KEY in env for production


@app.route("/", methods=["GET", "POST"])
def index():
    """
    Main page: shows form and (after POST) the generated travel plan.
    Checks required env keys on each request and shows friendly message if missing.
    """
    # check required environment variables
    missing = check_required_env()
    if missing:
        return render_template("index.html", missing=missing, result=None, example=None, error=None)

    # example placeholders
    example = {
        "destination": "Jaipur, India",
        "dates": "2025-12-10 to 2025-12-15",
        "budget": "50000",
        "mood": "adventure",
    }

    result = None
    error = None

    if request.method == "POST":
        destination = (request.form.get("destination") or "").strip()
        dates = (request.form.get("dates") or "").strip()
        budget = (request.form.get("budget") or "").strip()
        mood = (request.form.get("mood") or "").strip()

        if not destination or not budget or not mood:
            error = "Please fill Destination, Budget, and Mood."
            return render_template("index.html", missing=[], result=None, example=example, error=error)

        user_input = {
            "destination": destination,
            "dates": dates,
            "budget": budget,
            "mood": mood,
        }

        try:
            logger.info("Running travel crew for: %s", user_input)
            result = run_travel_crew(user_input)
            logger.info("Crew finished successfully.")
        except Exception as e:
            logger.exception("Crew error")
            error = str(e)
            result = None

    return render_template("index.html", missing=[], result=result, example=example, error=error)


@app.route("/healthz", methods=["GET"])
def health():
    return {"status": "ok"}
