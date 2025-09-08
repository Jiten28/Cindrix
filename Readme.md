# 🤖 Personal Gemini Assistant

An AI-powered personal assistant built with **Google Gemini API** and **Google Custom Search API**.
It can **remember conversations**, answer queries with **real-time data** (Bitcoin price, Weather), fetch **web & image search results**, and even **speak responses** using Text-to-Speech.

---

## 🚀 Features

* 🧠 **Conversation Memory** – remembers your past chats.
* 💱 **Live Bitcoin Price** – fetches real-time BTC price in USD & INR.
* 🌦️ **Weather Reports** – get current weather updates for cities worldwide.
* 🔎 **Web Search** – powered by Google Custom Search API.
* 🖼️ **Image Search** – retrieves top 3 images for your query.
* 🎙️ **Text-to-Speech (TTS)** – assistant speaks responses.
* 📜 **Logging & History** – saves all chats to `conv_history.json` and `chat_log.txt`.
* 🔄 **Gemini Fallback** – if real-time API/search fails, Gemini answers naturally.

---

## 📂 Project Structure

```
📦 Personal-Gemini-Assistant
 ┣ 📜 gemini_retrieval.py   # Main program
 ┣ 📜 conv_history.json     # Conversation memory (auto-created)
 ┣ 📜 chat_log.txt          # Logs of conversations
 ┣ 📜 .env                  # API keys & settings
 ┗ 📜 README.md             # Documentation
```

---

## ⚙️ Setup

### 1️⃣ Clone Repository

```bash
git clone https://github.com/Jiten28/Personal-Gemini.git
cd personal-gemini-assistant
```

### 2️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

**requirements.txt**

```
google-generativeai
python-dotenv
requests
pyttsx3
```

---

## 🔑 Environment Variables

Create a `.env` file in the project root:

```
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_CSE_ID=your_custom_search_engine_id_here
HISTORY_FILE=conv_history.json
```

👉 Keys you need:

* **Google API Key** → from [Google Cloud Console](https://console.cloud.google.com/)
* **Google Custom Search Engine ID (CSE ID)** → from [Google Custom Search](https://programmablesearchengine.google.com/)

---

## ▶️ Run the Assistant

```bash
python gemini_retrieval.py
```

Example interaction:


<img width="1084" height="850" alt="image" src="https://github.com/user-attachments/assets/a578d790-d055-4fb5-a383-aa47610fed7a" />



---

## 🛠️ How It Works

1. **Gemini API** → Handles natural conversation, structured JSON outputs (price, weather).
2. **Google Custom Search API** → Fetches real-time info & images.
3. **Conversation History** → Maintains context in `conv_history.json`.
4. **Logging** → Saves all chats in `chat_log.txt`.
5. **Text-to-Speech** → Reads responses aloud via `pyttsx3`.

---

## 📌 Notes

* If **Google Search API** fails, Gemini fallback ensures you always get a response.
* Weather & Bitcoin prices are extracted in **structured JSON** for natural replies.
* For images, only **top 3 links** are shown.

---
