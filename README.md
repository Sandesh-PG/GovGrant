# 🛡️ GovGrant AI: Autonomous Discovery for Indian MSMEs

**GovGrant AI** is a premium, multi-agent platform designed to bridge the gap between Indian government funding and the entrepreneurs who need it. By leveraging **Gemini 2.0 Flash** and autonomous web-scraping agents, we transform the complex world of government subsidies into a clear, actionable roadmap for business owners.

---

## 🚀 The Vision
Every year, billions in government grants go unclaimed due to information asymmetry and complex eligibility hurdles. GovGrant AI automates the research, validation, and planning phases, allowing MSMEs to find their perfect funding match in minutes.

---

## ✨ Key Features

### 1. **Midnight Premium UI**
- **Modern Aesthetic**: A high-contrast, "Midnight" themed interface built with glassmorphism and smooth animations.
- **Agentic Dashboard**: Real-time status tracking as our AI agents perform research on your behalf.
- **Deep-Scraped Reports**: Personalized results pages with roadmaps mined directly from official portals.

### 2. **Multi-Agent Orchestration**
- **Agent 1 (Intake)**: A conversational RAG-based agent that builds your business profile through natural dialogue.
- **Agent 2 (Researcher)**: An autonomous scraper that searches live government websites and extracts deep details like documents and application steps.
- **Agent 3 (Validator)**: Performs hard-eligibility checks and ranks schemes based on match probability and urgency.
- **Agent 4 (Planner)**: Synthesizes all research into a professional report with a step-by-step application roadmap.

### 3. **Intelligent Automation**
- **Quota-Efficient Pipeline**: Consolidated AI reasoning to minimize latency and prevent API rate limits.
- **Deep Scraping**: Mines required document lists and specific application portal names directly from the web.
- **Real-Time Data**: Uses a combination of verified internal datasets and live web discovery.

---

## 🛠️ Tech Stack

### **Frontend**
- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS + Lucide Icons
- **State**: React Hooks + LocalStorage Auth
- **Aesthetics**: Custom Glassmorphism & Framer Motion animations

### **Backend**
- **Framework**: FastAPI (Python 3.10+)
- **AI Engine**: Google Gemini 2.0 Flash (`google-genai`)
- **Database**: SQLModel (SQLAlchemy) + SQLite
- **Vector Search**: ChromaDB (for RAG-based intake)
- **Scraping**: Playwright + HTTPX + BeautifulSoup

---

## 📂 Project Structure

```bash
GovGrant/
├── govgrant-frontend/    # Next.js Application
│   ├── app/              # Routes (Home, Chat, Results)
│   ├── components/       # UI Components (GrantCard, Checklist)
│   └── lib/              # API utilities & types
└── govgrant-backend/     # FastAPI Application
    ├── agents/           # The 4 AI Agents (Intake, Research, Validator, Planner)
    ├── db/               # SQLModel schemas & database config
    ├── api/              # FastAPI routes
    └── scripts/          # Database migration & utility scripts
```

---

## 🏁 Getting Started

### 1. **Prerequisites**
- Node.js (v18+)
- Python (v3.10+)
- Google Gemini API Key

### 2. **Backend Setup**
```bash
cd govgrant-backend
pip install -r requirements.txt
# Set GOOGLE_API_KEY in .env
python scripts/migrate_db.py  # Initialize the database
uvicorn main:app --reload
```

### 3. **Frontend Setup**
```bash
cd govgrant-frontend
npm install
npm run dev
```

---

## 📄 License
This project was built for the **Deepstation Hackathon**. 🚀✨
