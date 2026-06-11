# 🗄️ AI SQL Assistant

> Convert plain English into executable SQL queries — instantly.

[![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-black?logo=flask)](https://flask.palletsprojects.com)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--3.5-412991?logo=openai)](https://openai.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🤖 AI Generation | OpenAI GPT-3.5 converts English → SQL |
| ⚙️ Offline Fallback | Rule-based engine when no API key is set |
| 🎨 Syntax Highlighting | Color-coded SQL output |
| ✅ SQL Validation | Checks keywords, semicolons, clauses |
| 📋 Copy Button | One-click clipboard copy |
| 🕑 History | Last 8 queries saved in localStorage |
| 📱 Responsive | Works on desktop & mobile |

---

## 🚀 Quick Start

### 1 — Clone & install

```bash
git clone https://github.com/invo-coder19/AI_SQL_Assistant.git
cd AI_SQL_Assistant
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

### 2 — Configure environment

```bash
copy .env.example .env       # Windows
# cp .env.example .env       # macOS / Linux
```

Open `.env` and set your key (optional — rule-based fallback works without it):

```
OPENAI_API_KEY=sk-your-key-here
```

### 3 — Run

```bash
python app.py
```

Open **http://localhost:5000** in your browser.

---

## 📁 Project Structure

```
AI_SQL_Assistant/
├── app.py                  # Flask app & API routes
├── requirements.txt
├── .env.example
├── services/
│   └── sql_generator.py    # AI + rule-based SQL engine
├── templates/
│   └── index.html          # Main UI
└── static/
    ├── style.css           # Premium dark-mode styles
    └── script.js           # Frontend logic
```

---

## 🔌 API

### `POST /generate`

```json
// Request
{ "query": "show all customers from Pune" }

// Response
{ "sql": "SELECT *\n    FROM customers\n    WHERE city = 'Pune';", "method": "openai" }
```

### `GET /health`

```json
{ "status": "ok", "service": "AI SQL Assistant" }
```

---

## 💡 Example Queries

```
Show all employees with salary greater than 50000
Find customers from Mumbai
Count total orders placed this month
Show top 10 products by sales
List students who scored above 80 marks
Find average salary by department
```

---

## 🛠️ Tech Stack

- **Backend:** Python · Flask · Flask-CORS
- **AI:** OpenAI GPT-3.5-turbo · Rule-based NLP fallback
- **Frontend:** Vanilla HTML · CSS · JavaScript
- **Design:** Dark glassmorphism · JetBrains Mono · Inter

---

## 📄 License

MIT © 2026 [invo-coder19](https://github.com/invo-coder19)
