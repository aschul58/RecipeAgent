# llm_answer.py
from __future__ import annotations
import os, json
from typing import List, Dict, Any
from openai import OpenAI

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def format_plan_with_llm(user_message: str, candidates: List[Dict[str, Any]]) -> str:
    """
    Nimmt deine tool_plan()-Ergebnisse und lässt das LLM eine kurze,
    fundierte Empfehlung formulieren (mit Begründung + Quelle).
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    compact = []
    for c in candidates[:5]:
        compact.append({
            "title": c.get("title"),
            "key_ingredients": (c.get("ingredients") or [])[:8],
            "source": c.get("enrichment_source","original"),
            "score": c.get("score", 0)
        })

    system = (
        "Du bist ein Küchen-Planungsassistent. "
        "Formuliere klare, kurze Empfehlungen (max. 6 Sätze), "
        "nenne 2–3 beste Optionen mit kurzer Begründung. "
        "Wenn passende Rezepte fehlen, sage es ehrlich und nenne pragmatische Alternativen."
    )
    user = (
        f"Nutzerfrage: {user_message}\n\n"
        f"Kandidaten (JSON):\n{json.dumps(compact, ensure_ascii=False)}\n\n"
        "Bitte antworte auf Deutsch. Ende."
    )

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":system},
                  {"role":"user","content":user}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()
