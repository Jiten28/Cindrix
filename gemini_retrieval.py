import os
import json
import logging
import google.generativeai as genai
import requests
import pyttsx3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
HISTORY_FILE = os.getenv("HISTORY_FILE", "conv_history.json")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")  # add in .env

# Configure Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# Setup logging
logging.basicConfig(
    filename="chat.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

# Text-to-Speech
engine = pyttsx3.init()
engine.setProperty("rate", 185)
engine.setProperty("volume", 1.0)

# ---------------- HISTORY ----------------
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and all("user" in d and "bot" in d for d in data):
                    return data
        except Exception:
            pass
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4)

# ---------------- GEMINI ----------------
def call_gemini(prompt):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text if response and response.text else "⚠️ No response from Gemini."
    except Exception as e:
        return f"❌ Gemini error: {str(e)}"

# ---------------- REAL APIs ----------------
def get_crypto_price(symbol="bitcoin", currency="usd"):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": symbol, "vs_currencies": currency}
        res = requests.get(url, params=params).json()
        price = res.get(symbol, {}).get(currency)
        if price:
            return f"The current price of {symbol.capitalize()} is {price:,} {currency.upper()}."
    except Exception as e:
        return None
    return None

def get_weather(city="Mumbai"):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"}
        res = requests.get(url, params=params).json()
        if res.get("main"):
            temp = res["main"]["temp"]
            desc = res["weather"][0]["description"]
            return f"The weather in {city} is {temp}°C with {desc}."
    except Exception:
        return None
    return None

# ---------------- GOOGLE SEARCH (fallback) ----------------
def search_google(query, search_type="web"):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"q": query, "key": GOOGLE_API_KEY, "cx": GOOGLE_CSE_ID}
    if search_type == "image":
        params["searchType"] = "image"
    try:
        res = requests.get(url, params=params).json()
        if "items" not in res:
            return None
        if search_type == "image":
            return f"Here’s an image: {res['items'][0]['link']}"
        else:
            return res["items"][0]["snippet"]
    except Exception:
        return None

# ---------------- QUERY HANDLER ----------------
def handle_query(user_input, history):
    text = user_input.lower()

    # Real APIs
    if "bitcoin" in text or "btc" in text or "crypto" in text:
        ans = get_crypto_price("bitcoin", "usd")
        if not ans:
            ans = search_google(user_input, "web")
        if not ans:
            ans = call_gemini(user_input)
        return ans

    if "weather" in text or "temperature" in text:
        city = "Mumbai"
        words = user_input.split()
        for w in words:
            if w.istitle():
                city = w
        ans = get_weather(city)
        if not ans:
            ans = search_google(user_input, "web")
        if not ans:
            ans = call_gemini(user_input)
        return ans

    # Other searches
    if "search" in text or "find" in text or "image" in text:
        search_type = "image" if "image" in text else "web"
        ans = search_google(user_input, search_type)
        if not ans:
            ans = call_gemini(user_input)
        return ans

    # Normal Gemini conversation
    conversation = "\n".join([f"User: {h['user']}\nAssistant: {h['bot']}" for h in history])
    full_prompt = f"{conversation}\nUser: {user_input}\nAssistant:"
    return call_gemini(full_prompt)

# ---------------- SPEAK ----------------
def speak(text):
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception:
        pass

# ---------------- MAIN ----------------
if __name__ == "__main__":
    print("🤖 Gemini Assistant ready! (type 'exit' to quit)\n")
    history = load_history()

    while True:
        user = input("You: ")
        if user.lower() in ["exit", "quit"]:
            print("👋 Goodbye!")
            save_history(history)
            break

        reply = handle_query(user, history)
        print(f"Assistant: {reply}\n")
        speak(reply)

        history.append({"user": user, "bot": reply})
        save_history(history)
        logging.info(f"USER: {user} | ASSISTANT: {reply}")
