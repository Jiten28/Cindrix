# 🤖 Personal Gemini AI Assistant

An intelligent assistant built with **Google Gemini API** + **Google Custom Search API**.  
It remembers chat history, answers questions, and retrieves **real-time web & image results**.

---

## 🚀 Features
- Conversational AI powered by **Google Gemini**.
- Memory: Remembers previous chat context.
- Real-time info: Integrated with **Google Search API**.
- Image search support.
- Logs all conversations into `chat.log`.
- Persistent history stored in `conv_history.json`.

---

## 📂 Project Structure
```

Personal-Gemini/
│── gemini\_retrieval.py   # main Python script
│── conv\_history.json     # auto-generated, stores chat history
│── .env                  # API keys + settings
│── requirements.txt      # dependencies
│── README.md             # documentation

````

---

## ⚙️ Setup Instructions

1. Clone the repo:
   ```bash
   git clone https://github.com/yourusername/personal-gemini.git
   cd personal-gemini
````

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a **.env file**:

   ```
   GOOGLE_API_KEY=your_google_api_key_here
   GOOGLE_CSE_ID=your_custom_search_engine_id_here
   HISTORY_FILE=conv_history.json
   ```

4. Run the assistant:

   ```bash
   python gemini_retrieval.py
   ```

---

## 💡 Example Usage

```
🤖 Gemini Assistant ready! (type 'exit' to quit)

You: hi
Assistant: Hello! How can I assist you today?

You: search latest bitcoin price
Assistant: Bitcoin Price Today: https://www.coindesk.com/... 
...

You: search image sunset in mumbai
Assistant: 
https://image-link-1.jpg
https://image-link-2.jpg
```

---

## 🛠️ Tech Stack

* **Python 3.12+**
* **Google Gemini API** (`google-generativeai`)
* **Google Custom Search API**
* **dotenv** for environment management
* **requests** for API calls
* **logging + JSON** for history persistence

---
