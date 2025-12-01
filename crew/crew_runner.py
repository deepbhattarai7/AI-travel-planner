# crew/crew_runner.py — optimized orchestration with caching & concurrency
import os
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from .agents import (
    BudgetAgent, TrendAnalyzerAgent, ItineraryBuilderAgent,
    HotelFinderAgent, FoodFinderAgent, unsplash_search
)

REQUIRED_KEYS = ["GEMINI_API_KEY", "UNSPLASH_ACCESS_KEY"]

def check_required_env():
    missing = []
    for k in REQUIRED_KEYS:
        if not os.getenv(k):
            missing.append(k)
    return missing


# Instances of agents (instantiate once per process)
_budget_agent = BudgetAgent()
_trend_agent = TrendAnalyzerAgent()
_itinerary_agent = ItineraryBuilderAgent()
_hotel_agent = HotelFinderAgent()
_food_agent = FoodFinderAgent()

# Simple file-cache (per input) to reduce repeated heavy API calls
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", ".travel_cache.json")
CACHE_LOCK = threading.Lock()
# default TTL 3600 seconds (1 hour) — override with TRAVEL_CACHE_TTL env var if desired
CACHE_TTL = int(os.getenv("TRAVEL_CACHE_TTL", "3600"))


def _load_cache():
    try:
        with CACHE_LOCK:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r", encoding="utf-8") as fh:
                    return json.load(fh)
    except Exception:
        pass
    return {}


def _save_cache(cache_dict):
    try:
        with CACHE_LOCK:
            with open(CACHE_FILE, "w", encoding="utf-8") as fh:
                json.dump(cache_dict, fh)
    except Exception:
        pass


def _cache_key(destination, dates, budget, mood):
    # stable key — strip and lowercase destination & mood
    return f"{destination.strip().lower()}|{dates.strip()}|{budget}|{mood.strip().lower()}"


def _get_cached(key):
    cache = _load_cache()
    entry = cache.get(key)
    if not entry:
        return None
    ts = entry.get("_ts", 0)
    if time.time() - ts > CACHE_TTL:
        # expired
        return None
    return entry.get("value")


def _set_cached(key, value):
    cache = _load_cache()
    cache[key] = {"_ts": int(time.time()), "value": value}
    _save_cache(cache)


# run function with a timeout using ThreadPoolExecutor (simple wrapper)
def _run_with_timeout(fn, *args, timeout=18):
    """
    Runs fn(*args) in a short-lived thread with a timeout (seconds).
    Returns tuple (ok, result_or_exception).
    """
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn, *args)
        try:
            res = fut.result(timeout=timeout)
            return True, res
        except TimeoutError as te:
            return False, TimeoutError(f"Timeout after {timeout}s for {fn.__name__}")
        except Exception as e:
            return False, e


def run_travel_crew(user_input):
    """
    Orchestrates agents with concurrency + caching.
    Returns the same result structure as before — no change in output format or counts.
    """
    destination = (user_input.get("destination") or "").strip()
    dates = (user_input.get("dates") or "").strip()
    budget = (user_input.get("budget") or "").strip()
    mood = (user_input.get("mood") or "relax").strip()

    if not destination or not budget:
        raise ValueError("destination and budget are required")

    key = _cache_key(destination, dates, budget, mood)
    cached = _get_cached(key)
    if cached:
        # return deep copy to avoid accidental mutation by caller
        return json.loads(json.dumps(cached))

    # 1) Budget analysis (fast, local)
    budget_info = _budget_agent.run(budget, dates)

    # 2) Trends — needed for itinerary
    ok, trends_or_err = _run_with_timeout(_trend_agent.run, destination, timeout=20)
    if not ok:
        # trend failure — fallback to empty list but continue
        trends = []
    else:
        trends = trends_or_err or []

    # 3) Run itinerary, hotels, foods, and gallery concurrently (they are independent now)
    itinerary = []
    hotels = []
    foods = []
    gallery = []

    # define worker tasks
    task_map = {
        "itinerary": lambda: _itinerary_agent.run(destination, mood, budget_info, trends),
        "hotels": lambda: _hotel_agent.run(destination, budget_info),
        "foods": lambda: _food_agent.run(destination, mood, budget_info),
        "gallery": lambda: unsplash_search(destination, per_page=6)  # keep full gallery per your request
    }

    # run with ThreadPoolExecutor with a few workers — use conservative timeouts to avoid hangs
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_to_name = {pool.submit(func): name for name, func in task_map.items()}

        # allow a reasonable overall wait; collect results as they arrive
        for fut in as_completed(future_to_name, timeout=40):
            name = future_to_name[fut]
            try:
                # ensure we also bound individual waiting to avoid deadlocks
                res = fut.result(timeout=8)
            except Exception:
                # on any failure, keep fallback empty (do not alter other results)
                res = []
            if name == "itinerary":
                itinerary = res or []
            elif name == "hotels":
                hotels = res or []
            elif name == "foods":
                foods = res or []
            elif name == "gallery":
                gallery = res or []

    # 4) Fallbacks and final structure
    result = {
        "destination": destination,
        "dates": dates,
        "mood": mood,
        "budget_info": budget_info,
        "trends": trends,
        "photos": gallery,
        "itinerary": itinerary,
        "hotels": hotels,
        "foods": foods
    }

    # 5) Cache the full result to reduce repeated heavy calls
    try:
        _set_cached(key, result)
    except Exception:
        pass

    return result
