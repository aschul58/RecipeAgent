# RecipeAgent
Agent for accessing and consulting my own recipes

Everyone cooks differently. Over time, I’ve collected my own recipes — from my mom, grandma, friends, or things I’ve improvised myself — and stored them in a personal Notion page.  
That’s why searching the web or asking ChatGPT for recipes often doesn’t help: I don’t want random “internet recipes”, I want to use *my* recipes and *my* way of cooking.

**Recipe Agent** is a small project that connects directly to my Notion recipe collection and turns it into an intelligent personal cooking assistant.  
It can read, structure, and enrich my own recipes — and then help me decide what to cook based on the ingredients I have at home.

---

## Why and How It Works

### 1. Notion Integration – accessing my personal recipe collection
**Purpose:**  
All my recipes live in one long Notion page — some are detailed, some are just rough notes.  
The agent needs to read these directly from my workspace.

**Implementation:**  
A Notion API integration extracts each recipe, even if it’s unstructured or incomplete.  
The script parses paragraphs, dividers, and bullet points into structured objects with fields like `title`, `body`, `ingredients`, and `steps`.  
This forms the foundation of the agent’s “memory”.

---

### 2. Enrichment Pipeline – filling the gaps
**Purpose:**  
Many of my recipes only contain titles or a few lines.  
The goal is to automatically fill in missing parts like ingredients or cooking steps.

**Implementation:**  
Each recipe is checked for completeness using a simple text heuristic (number of lines, cooking terms, etc.).  
If the recipe is incomplete, the agent enriches it by querying the **Spoonacular API** or, as a fallback, an **OpenAI model** (GPT-4o-mini).  
The enriched data (ingredients and steps) is cached locally in `enrichment_cache.json` for later reuse.

---

### 3. Recipe Agent Logic – reasoning about what to cook
**Purpose:**  
When I say something like:  
> “I have carrots and onions, what can I cook?”  
the agent should match that against my recipes and suggest the best options.

**Implementation:**  
This layer performs simple intent recognition and keyword matching between user input and the available recipes.  
It can also delegate to the OpenAI API to generate a natural-language response.  
The result is a ranked list of recipes from my personal collection, optionally enriched with missing details.

---

### 4. FastAPI Backend – making it accessible
**Purpose:**  
To make the agent modular and testable, all logic is wrapped into a REST API.

**Implementation:**  
A lightweight **FastAPI** service exposes endpoints like `/chat` and `/plan`.  
It takes user messages as input, processes them through the agent, and returns structured JSON responses.  
The backend can be started locally or containerized for deployment.

---

### 5. Streamlit Frontend – a simple UI for interaction
**Purpose:**  
To interact with the system easily without the command line.

**Implementation:**  
A **Streamlit** app (`ui.py`) provides a small web interface.  
It lets you enter natural-language queries, toggle the LLM option, and view the matched recipes and suggestions in a clean format.  
The app communicates with the FastAPI backend in real time.

---

## Architecture Overview


- `notion_api.py` – handles data access and parsing from Notion  
- `enrichment.py` – checks for completeness and enriches missing recipes  
- `agent.py` – interprets natural language queries and matches recipes  
- `app.py` – FastAPI backend exposing `/chat` and `/plan` endpoints  
- `ui.py` – Streamlit web interface for interaction  
- `.env` – local environment file for storing API keys and configuration

---

## Technologies

| Component | Tools |
|------------|--------|
| Backend | Python 3.12, FastAPI |
| Frontend | Streamlit |
| APIs | Notion API, Spoonacular API |
| AI | OpenAI API (GPT-4o-mini) |
| Utilities | dotenv, requests, uvicorn |

