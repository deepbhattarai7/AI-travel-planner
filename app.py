# app.py — Full Flask 3.x compatible entrypoint for Mood & Budget Travel Planner
import os
import traceback
from flask import Flask, render_template, request

# Import orchestration helpers from crew package
from crew.crew_runner import run_travel_crew, check_required_env

# Load environment variables from .env (if present)
import os

# DIRECT API KEYS HERE
os.environ["GEMINI_API_KEY"] = "AIzaSyBx_Zmwc2rPvwNCcodIgvgz8jyAL3OwHQQ"
os.environ["UNSPLASH_ACCESS_KEY"] = "mMtGiYOvRm4MaAk19vgiSVgVI4eX-nanBCfPNYEyO3o"
os.environ["SECRET_KEY"] = "supersecret123ysjjjsgggshsh"


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")  # keep a secure SECRET_KEY in production


@app.route("/", methods=["GET", "POST"])
def index():
    """
    Main page: shows form and (after POST) the generated travel plan.
    This implementation checks required env keys on each request (works across Flask versions).
    """
    # 1) Ensure required env keys exist
    missing = check_required_env()
    if missing:
        # Render index with a clear message about missing environment variables
        return render_template(
            "index.html",
            missing=missing,
            result=None,
            example=None,
            error=None
        )

    # Example placeholders shown in the form
    example = {
        "destination": "Jaipur, India",
        "dates": "2025-12-10 to 2025-12-15",
        "budget": "50000",
        "mood": "adventure",
    }

    result = None
    error = None

    if request.method == "POST":
        # 2) Read and validate form inputs
        destination = (request.form.get("destination") or "").strip()
        dates = request.form.get("dates")
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

        # 3) Run the multi-agent crew and catch runtime issues
        try:
            print("\n--- USER INPUT ---")
            print(user_input)

            try:
                result = run_travel_crew(user_input)
                print("\n--- CREW RESULT ---")
                print(result)
            except Exception as e:
                print("\n--- CREW ERROR ---")
                print(e)
                import traceback
                traceback.print_exc()
                result = None
                error = str(e)

        except Exception as e:
            # Log traceback to console for debugging; present a friendly error to user
            traceback.print_exc()
            error = f"Failed to generate plan: {str(e)}"
            return render_template("index.html", missing=[], result=None, example=example, error=error)

    # 4) Render page with results (or form if GET)
    return render_template("index.html", missing=[], result=result, example=example, error=error)


@app.route("/healthz", methods=["GET"])
def health():
    """Simple health check endpoint for Render / monitoring."""
    return {"status": "ok"}




