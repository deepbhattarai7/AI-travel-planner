from .agents import (
    BudgetAgent, TrendAnalyzerAgent, ItineraryBuilderAgent,
    HotelFinderAgent, FoodFinderAgent, unsplash_search
)
import os

REQUIRED_KEYS = ["GEMINI_API_KEY", "UNSPLASH_ACCESS_KEY"]

def check_required_env():
    missing = []
    for k in REQUIRED_KEYS:
        if not os.getenv(k):
            missing.append(k)
    return missing


def run_travel_crew(user_input):
    """
    Orchestrate agents. Raises RuntimeError on failure.
    user_input must contain: destination, dates, budget, mood
    """
    destination = user_input.get("destination")
    dates = user_input.get("dates", "")
    budget = user_input.get("budget")
    mood = user_input.get("mood", "relax")

    if not destination or not budget:
        raise ValueError("destination and budget are required")

    # Instantiate agents
    budget_agent = BudgetAgent()
    trend_agent = TrendAnalyzerAgent()
    itinerary_agent = ItineraryBuilderAgent()
    hotel_agent = HotelFinderAgent()
    food_agent = FoodFinderAgent()

    # 1. Budget analysis
    budget_info = budget_agent.run(budget, dates)

    # 2. Trends + spot photos
    spots = trend_agent.run(destination)

    # 3. Itinerary (Gemini uses spots)
    itinerary = itinerary_agent.run(destination, mood, budget_info, spots)

    # 4. Hotels (Gemini + Unsplash)
    hotels = hotel_agent.run(destination, budget_info)

    # 5. Food
    foods = food_agent.run(destination, mood, budget_info)

    # 6. Fetch a gallery of Unsplash photos for the destination (for hero gallery)
    try:
        gallery = unsplash_search(destination, per_page=6)
    except Exception:
        gallery = []

    result = {
        "destination": destination,
        "dates": dates,
        "mood": mood,
        "budget_info": budget_info,
        "trends": spots,
        "photos": gallery,
        "itinerary": itinerary,
        "hotels": hotels,
        "foods": foods
    }
    return result
