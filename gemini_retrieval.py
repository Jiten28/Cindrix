import os
import re
import json
import logging
import requests
import google.generativeai as genai
from dotenv import load_dotenv
import pyttsx3

# -------------------- ENV & CONFIG --------------------
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "").strip()
HISTORY_FILE = os.getenv("HISTORY_FILE", "conv_history.json")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

logging.basicConfig(
    filename="chat.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

# TTS
_tts = pyttsx3.init()
_tts.setProperty("rate", 185)
_tts.setProperty("volume", 1.0)

def speak(text: str):
    try:
        _tts.say(text)
        _tts.runAndWait()
    except Exception:
        pass

# -------------------- HISTORY --------------------
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and all(isinstance(x, dict) for x in data):
                    return data
        except Exception:
            pass
    return []

def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# -------------------- GEMINI --------------------
def call_gemini(prompt: str) -> str:
    if not GOOGLE_API_KEY:
        return "Gemini is not configured (missing GOOGLE_API_KEY)."
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt)
        return (resp.text or "").strip() if resp else "No response."
    except Exception as e:
        return f"(Gemini error: {e})"

def call_gemini_json(prompt: str):
    """Ask Gemini to respond with a single JSON object. Returns dict or None."""
    text = call_gemini(prompt)
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception:
        return None
    return None

# -------------------- REAL DATA APIS --------------------
def get_crypto_price(symbol="bitcoin"):
    """
    Real-time via CoinGecko (no API key required).
    Returns natural sentence with USD & INR if available.
    """
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": symbol, "vs_currencies": "usd,inr"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get(symbol, {})
        usd = data.get("usd")
        inr = data.get("inr")
        if usd is None and inr is None:
            return None
        parts = []
        if usd is not None:
            parts.append(f"{usd:,.2f} USD")
        if inr is not None:
            parts.append(f"{inr:,.2f} INR")
        return f"The current price of {symbol.capitalize()} is " + " or ".join(parts) + "."
    except Exception:
        return None

def get_weather_openweather(city: str):
    """
    Current weather via OpenWeather (requires OPENWEATHER_API_KEY).
    Returns a natural sentence or None on failure.
    """
    if not OPENWEATHER_API_KEY:
        return None
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        js = r.json()
        if js.get("cod") != 200:
            return None
        temp = js["main"]["temp"]
        desc = js["weather"][0]["description"]
        hum = js["main"].get("humidity")
        wind = js.get("wind", {}).get("speed")
        extra = []
        if hum is not None:
            extra.append(f"humidity {hum}%")
        if wind is not None:
            extra.append(f"wind {wind} m/s")
        tail = f" ({', '.join(extra)})" if extra else ""
        return f"The weather in {city} is {temp:.1f}°C with {desc}{tail}."
    except Exception:
        return None

def get_weather_gemini(city: str):
    """
    Gemini fallback phrasing (not guaranteed real-time).
    """
    prompt = f"""
You are a concise weather assistant. If you don't have live data, give a best-effort estimate and speak naturally.
Return ONLY a JSON object:
{{
  "temperature_C": number,
  "description": "string",
  "note": "string (e.g., 'approximate')"
}}
City: {city}
"""
    data = call_gemini_json(prompt)
    if data and "temperature_C" in data and "description" in data:
        note = f" ({data.get('note')})" if data.get("note") else ""
        return f"The weather in {city} is about {data['temperature_C']}°C with {data['description']}.{note}"
    # fallback to plain text if JSON fails
    txt = call_gemini(f"Briefly describe the current weather in {city}. Keep it to one sentence.")
    return txt or f"Sorry, I couldn't determine the weather for {city}."

# -------------------- GOOGLE CUSTOM SEARCH --------------------
def google_search(query: str, search_type: str = "web"):
    """
    search_type: "web" or "image"
    Returns list of snippets (web) or list of image URLs (image); None on failure.
    """
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        return None
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"q": query, "key": GOOGLE_API_KEY, "cx": GOOGLE_CSE_ID}
        if search_type == "image":
            params["searchType"] = "image"
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        js = r.json()
        items = js.get("items", [])
        if not items:
            return None
        if search_type == "image":
            return [it.get("link") for it in items[:3] if it.get("link")]
        else:
            return [it.get("snippet", "") for it in items[:3]]
    except Exception:
        return None

# -------------------- NLP HELPERS --------------------
CITY_HINTS = ["mumbai", "hyderabad", "delhi", "bangalore", "bengaluru", "chennai", "kolkata",
              "pune", "london", "new york", "tokyo", "paris", "san francisco"]

def extract_city(text: str, default="Hyderabad"):
    text_low = text.lower()
    # pattern: "... in <city>"
    m = re.search(r"\bin\s+([a-zA-Z\s]+)$", text_low)
    if m:
        city = m.group(1).strip().title()
        return city
    # look for known hints
    for c in CITY_HINTS:
        if c in text_low:
            return c.title()
    # if user wrote just a city name
    tokens = [t for t in re.split(r"[^A-Za-z]+", text) if t]
    if len(tokens) == 1:
        return tokens[0].title()
    return default

# -------------------- ROUTER --------------------
def handle_query(user_input: str, history: list):
    q = user_input.strip()
    ql = q.lower()

    # --- Crypto ---
    if any(k in ql for k in ["bitcoin", "btc", "crypto", "price"]):
        ans = get_crypto_price("bitcoin")
        if not ans:
            # fallback web snippet…
            snips = google_search(q, "web")
            if snips:
                # try to extract a number like 12345.67
                joined = " ".join(snips)
                m = re.search(r"\b(\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?)\b", joined)
                if m:
                    ans = f"Approximate Bitcoin price I found: {m.group(1)}."
        if not ans:
            # final fallback to Gemini
            ans = call_gemini("Give a short, natural sentence with the latest Bitcoin price if you know it. If not, say you can't access live data.")
        return ans

    # --- Weather ---
    if any(k in ql for k in ["weather", "temperature", "forecast"]):
        city = extract_city(q, default="Hyderabad")
        ans = get_weather_openweather(city)
        if not ans:  # fallback to Gemini phrasing
            ans = get_weather_gemini(city)
        return ans

    # --- Image search ---
    if "image" in ql or "picture" in ql or "photos" in ql:
        # remove common prefixes
        cleaned = re.sub(r"\b(images?|pictures?|photos?)\b|\b(of|about|for)\b", "", q, flags=re.IGNORECASE).strip()
        cleaned = cleaned or q
        imgs = google_search(cleaned, "image")
        if imgs:
            return "Top images:\n" + "\n".join(imgs)
        # fallback to Gemini description
        return call_gemini(f"Describe three typical images you might find for: {cleaned}. Keep each description short.")

    # --- Web search (explicit) ---
    if any(k in ql for k in ["search", "google this", "find on google"]):
        snips = google_search(q, "web")
        if snips:
            return "Here’s what I found:\n- " + "\n- ".join(snips)
        return call_gemini(f"Answer concisely: {q}")

    # --- Clear history ---
    if ql in {"clear history", "reset memory", "wipe memory"}:
        save_history([])
        return "Conversation history cleared."

    # --- Chit-chat with memory ---
    context = "\n".join([f"User: {h['user']}\nAssistant: {h['bot']}" for h in history[-10:]])
    prompt = f"""{context}
User: {q}
Assistant: Respond helpfully in 1–3 sentences."""
    return call_gemini(prompt)

# -------------------- MAIN LOOP --------------------
if __name__ == "__main__":
    print("🤖 Gemini Assistant ready! (type 'exit' to quit)\n")
    if not GOOGLE_API_KEY:
        print("! WARNING: GOOGLE_API_KEY not set. Gemini & Custom Search won't work.")
    if not GOOGLE_CSE_ID:
        print("! NOTE: GOOGLE_CSE_ID not set. Web/Image search disabled.")
    if not OPENWEATHER_API_KEY:
        print("! NOTE: OPENWEATHER_API_KEY not set. Weather will use Gemini (approximate).")

    history = load_history()

    while True:
        user = input("You: ").strip()
        if user.lower() in {"exit", "quit"}:
            print("Assistant: Goodbye! 👋")
            break

        reply = handle_query(user, history)
        print("Assistant:", reply, "\n")
        speak(reply)

        history.append({"user": user, "bot": reply})
        save_history(history)
        logging.info("USER: %s", user)
        logging.info("ASSISTANT: %s", reply)
