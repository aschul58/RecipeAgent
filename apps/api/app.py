# app.py
# ------------------------------------------------------------
# FastAPI-Wrapper für deinen Recipe-Agent
# Endpoints:
#   GET  /health
#   POST /chat   { message, session_id? }
#   POST /plan   { pantry, exclude?, top_k?, strict? }
# Optional: CORS für lokale UIs (Streamlit etc.)
# ------------------------------------------------------------

from __future__ import annotations
import os
from typing import List, Optional, Any, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Eigene Module
from recipe_agent.agent import handle, tool_plan

load_dotenv()  # liest .env im Projektroot

# ---------------- FastAPI Setup ----------------

app = FastAPI(
    title="Recipe Agent API",
    version="0.1.0",
    description="Kleiner Agent zum Kochen-Planen auf Basis deiner Notion-Rezepte.",
)

# CORS (optional: für lokale UIs)
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8501").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Schemas ----------------

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    use_llm: Optional[bool] = False

class ChatResponse(BaseModel):
    intent: str
    reply: str
    suggestions: Optional[List[str]] = None
    results: Optional[List[Dict[str, Any]]] = None

class PlanRequest(BaseModel):
    pantry: str
    exclude: Optional[List[str]] = []
    top_k: Optional[int] = 5
    strict: Optional[bool] = True

class PlanItem(BaseModel):
    title: str
    ingredients: Optional[List[str]] = None
    steps: Optional[List[str]] = None
    enrichment_source: Optional[str] = "original"
    score: int

class PlanResponse(BaseModel):
    query: str
    items: List[PlanItem]

# ---------------- Routes ----------------

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    out = handle(req.message, use_llm=bool(req.use_llm))
    return ChatResponse(
        intent=out.get("intent","unknown"),
        reply=out.get("reply",""),
        suggestions=out.get("suggestions"),
        results=out.get("results"),
    )

@app.post("/plan", response_model=PlanResponse)
def plan(req: PlanRequest):
    """
    Direktes Planen auf Basis einer Pantry-Query (ohne freien Chat).
    """
    items = tool_plan(
        pantry_query=req.pantry,
        top_k=req.top_k or 5,
        strict=bool(req.strict),
        exclude=req.exclude or [],
    )
    # Map in Pydantic-Model
    mapped = [
        PlanItem(
            title=i.get("title", ""),
            ingredients=i.get("ingredients"),
            steps=i.get("steps"),
            enrichment_source=i.get("enrichment_source", "original"),
            score=int(i.get("score", 0)),
        )
        for i in items
    ]
    return PlanResponse(query=req.pantry, items=mapped)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/", include_in_schema=False)
def root():
    # Entweder auf Swagger weiterleiten:
    return RedirectResponse(url="/docs")