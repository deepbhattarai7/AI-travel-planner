import os
import json
import requests

# Gemini (google-generativeai)
GEMINI_KEY ='AIzaSyBx_Zmwc2rPvwNCcodIgvgz8jyAL3OwHQQ'
if GEMINI_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
    except Exception as e:
        # If import fails, keep GEMINI_KEY but log at runtime
        print("Warning: google.generativeai import failed:", e)

# Unsplash
UNSPLASH_KEY = 'mMtGiYOvRm4MaAk19vgiSVgVI4eX-nanBCfPNYEyO3o'
UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"


def unsplash_search(query, per_page=6):
    """Return list of image URLs from Unsplash for `query`. Raises if key missing."""
    if not UNSPLASH_KEY:
        raise RuntimeError("UNSPLASH_ACCESS_KEY is not set")
    headers = {"Authorization": f"Client-ID {UNSPLASH_KEY}"}
    params = {"query": query, "per_page": per_page}
    r = requests.get(UNSPLASH_API_URL, headers=headers, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    return [item["urls"]["regular"] for item in data.get("results", [])]

def call_gemini_text(prompt, max_tokens=400):
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")

    try:
        # IMPORTANT: Force raw JSON output
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config={
                "response_mime_type": "application/json"
            }
        )

        response = model.generate_content(prompt)

        # The response is EXACT JSON now
        text = response.text.strip()
        return text

    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}")



class BudgetAgent:
    def run(self, budget_str, dates_str):
        try:
            budget = float(budget_str)
        except Exception:
            raise ValueError("Budget must be a number")

        # Parse dates like "YYYY-MM-DD to YYYY-MM-DD"
        days = 5
        try:
            parts = dates_str.split("to")
            if len(parts) == 2:
                from datetime import datetime
                start = datetime.fromisoformat(parts[0].strip())
                end = datetime.fromisoformat(parts[1].strip())
                delta = (end - start).days + 1
                if delta > 0:
                    days = delta
        except Exception:
            # if parsing fails, default days remains
            pass

        per_day = round(budget / max(days, 1), 2)
        allocation = {"hotel_pct": 0.4, "food_pct": 0.3, "travel_pct": 0.2, "misc_pct": 0.1}
        breakdown = {k: round(per_day * v, 2) for k, v in allocation.items()}

        return {"total_budget": budget, "days": days, "per_day": per_day, "breakdown": breakdown}


class TrendAnalyzerAgent:
    """
    Uses Gemini to request a JSON array of trending spots for destination.
    Then enriches each spot with an Unsplash photo (search by spot name or destination).
    """

    def run(self, destination, top_k=5):
        # Prompt Gemini for JSON list: [{"name":"...", "desc":"...", "lat":.., "lon":..}, ...]
        prompt = (
            f"Provide up to {top_k} trending tourist spots for '{destination}'. "
            "Output only valid JSON array. Each item must include: name (string), "
            "desc (one-sentence string). Coordinates (lat, lon) are optional if unknown. "
            "Example output: [{'{'}\"name\":\"Spot 1\",\"desc\":\"...\"{'}'}, ...]"
        )
        raw = call_gemini_text(prompt, max_tokens=600)
        # Try to parse JSON from the response
        spots = []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for item in parsed:
                    name = item.get("name")
                    desc = item.get("desc", "")
                    lat = item.get("lat")
                    lon = item.get("lon")
                    if name:
                        spots.append({"name": name, "desc": desc, "lat": lat, "lon": lon})
        except Exception:
            # If parsing fails, try to extract lines heuristically (fallback to error)
            raise RuntimeError("Failed to parse Gemini response for trending spots. Response was:\n" + raw)

        # Attach photos using Unsplash. For each spot, search "spot name destination"
        for s in spots:
            q = f"{s['name']} {destination}"
            try:
                imgs = unsplash_search(q, per_page=3)
                s['image'] = imgs[0] if imgs else None
            except Exception:
                s['image'] = None

        return spots


class ItineraryBuilderAgent:
    """
    Uses Gemini to build a day-wise itinerary given spots, mood, dates, budget info.
    Returns list of days with summary and places and estimated cost.
    """
    def run(self, destination, mood, budget_info, spots):
        days = budget_info.get("days", 5)
        # Prepare a prompt that includes spots (names), mood, days and budget per day.
        spots_list = [s['name'] for s in spots]
        prompt = (
            f"Create a {days}-day itinerary for {destination} for someone with mood '{mood}'. "
            f"Budget per day: {budget_info.get('per_day')}. Use these spots: {spots_list}. "
            "Output JSON array of objects with fields: day (int), summary (string), places (list of names), est_cost (number)."
        )
        raw = call_gemini_text(prompt, max_tokens=700)
        try:
            parsed = json.loads(raw)
            # Validate and return
            itinerary = []
            for item in parsed:
                day = int(item.get("day"))
                summary = item.get("summary", "")
                places = item.get("places", [])
                est_cost = float(item.get("est_cost", budget_info.get("per_day", 0)))
                itinerary.append({"day": day, "summary": summary, "places": places, "est_cost": est_cost})
            return itinerary
        except Exception:
            raise RuntimeError("Failed to parse Gemini itinerary response. Response:\n" + raw)


class HotelFinderAgent:
    """
    Uses Gemini to suggest hotels (names + short desc). For images, we query Unsplash for each hotel name + destination.
    """
    def run(self, destination, budget_info, limit=3):
        prompt = (
            f"Suggest {limit} hotels in {destination} appropriate for a per-night hotel budget around {round(budget_info['breakdown']['hotel_pct'],2)}. "
            "Output JSON array of objects: name (string), price_per_night (number or string), rating (number 0-5)."
        )
        raw = call_gemini_text(prompt, max_tokens=400)
        hotels = []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for h in parsed:
                    name = h.get("name")
                    price = h.get("price_per_night")
                    rating = h.get("rating")
                    if name:
                        hotels.append({"name": name, "price_per_night": price, "rating": rating})
        except Exception:
            raise RuntimeError("Failed to parse Gemini hotels response. Response:\n" + raw)

        # Attach images
        for i, h in enumerate(hotels):
            try:
                imgs = unsplash_search(f"{h['name']} {destination}", per_page=2)
                h['image'] = imgs[0] if imgs else None
            except Exception:
                h['image'] = None

        return hotels


class FoodFinderAgent:
    """
    Uses Gemini to suggest restaurants or food spots; attach Unsplash photos for the place/food.
    """
    def run(self, destination, mood, budget_info, limit=4):
        prompt = (
            f"Suggest {limit} restaurants or food spots in {destination} for someone with mood '{mood}'. "
            "Output JSON array of objects: name (string), cuisine (string), price_range (string)."
        )
        raw = call_gemini_text(prompt, max_tokens=500)
        foods = []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for f in parsed:
                    name = f.get("name")
                    cuisine = f.get("cuisine")
                    price = f.get("price_range")
                    if name:
                        foods.append({"name": name, "type": cuisine, "price": price})
        except Exception:
            raise RuntimeError("Failed to parse Gemini restaurants response. Response:\n" + raw)

        # Attach images
        for f in foods:
            try:
                imgs = unsplash_search(f"{f['name']} {destination} food", per_page=1)
                f['image'] = imgs[0] if imgs else None
            except Exception:
                f['image'] = None

        return foods

