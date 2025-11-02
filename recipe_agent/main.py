# main.py
# ------------------------------------------------------------
# MVP-CLI: Suche nach Rezepten anhand vorhandener Zutaten.
# Flow:
#   - Lade Rezepte aus Notion
#   - Keyword-Vorfilter (schnell, ohne LLM)
#   - Enrichment nur für Kandidaten
#   - Re-Scoring anhand Zutaten-Treffern
#   - Ausgabe Top-N
#
# Aufrufbeispiele:
#   py main.py "karotte, zwiebel"
#   py main.py "feta tomaten"
# ------------------------------------------------------------

from __future__ import annotations
import sys
import re
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv

from notion_api import get_recipes
from recipe_agent.enrichment import enrich_if_needed
from recipe_agent.query_recipes import search_recipes  # nutzt deinen Keyword-Vorfilter

load_dotenv()

WORD_RX = re.compile(r"[A-Za-zÄÖÜäöüß0-9]+")

def tokenize(text: str) -> List[str]:
    return [w.lower() for w in WORD_RX.findall(text or "")]

def dedup_keep_order(xs: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def rescoring_by_ingredients(
    merged_recipe: Dict[str, Any],
    pantry_tokens: List[str]
) -> int:
    """
    Einfacher Re-Score:
      +3 pro Token-Treffer in ingredients
      +1 pro Token-Treffer im body (als Fallback)
      +2 Bonus, wenn >=2 Tokens in ingredients matchen
    """
    ingr = " ".join(merged_recipe.get("ingredients") or []).lower()
    body = (merged_recipe.get("body") or "").lower()

    hits_ing = sum(1 for t in pantry_tokens if t in ingr)
    hits_body = sum(1 for t in pantry_tokens if t in body)

    score = hits_ing * 3 + hits_body * 1
    if hits_ing >= 2:
        score += 2
    return score

def plan(query: str, top_k: int = 5, strict: bool = True) -> List[Dict[str, Any]]:
    """
    End-to-end Suche:
      1) Keyword-Vorfilter (query_recipes)
      2) Enrichment pro Kandidat
      3) Re-Scoring
    Rückgabe: Liste von {title, score, ingredients, steps, enrichment_source}
    """
    # 1) Vorfilter
    pre = search_recipes(query, recipes=None, must_include_all=strict, top_k=12)

    # 2) Pantry-Tokens
    pantry_tokens = dedup_keep_order([t for t in tokenize(query) if len(t) > 1])

    # 3) Enrichment + Re-Score
    enriched_ranked = []
    for item in pre:
        merged = enrich_if_needed({"title": item["title"], "body": item.get("body", "")})
        score = rescoring_by_ingredients(merged, pantry_tokens)
        enriched_ranked.append({
            "title": merged.get("title"),
            "ingredients": merged.get("ingredients", []),
            "steps": merged.get("steps", []),
            "body": merged.get("body", ""),
            "enrichment_source": merged.get("enrichment_source", "original"),
            "score": score
        })

    enriched_ranked.sort(key=lambda x: x["score"], reverse=True)
    return enriched_ranked[:top_k]

def pretty(results: List[Dict[str, Any]], query: str):
    if not results:
        print(f"Keine Treffer für: {query}")
        return
    print(f"\nBeste Vorschläge für: {query}\n")
    for i, r in enumerate(results, 1):
        src = r.get("enrichment_source", "original")
        print(f"{i}. {r['title']}  (score={r['score']}, quelle={src})")
        # kurze Vorschau Zutaten/Steps
        if r.get("ingredients"):
            preview_ing = ", ".join(r["ingredients"][:6])
            print("   Zutaten:", preview_ing + (" ..." if len(r["ingredients"]) > 6 else ""))
        elif r.get("body"):
            # Fallback: erste 2 Zeilen aus Body
            lines = [ln for ln in r["body"].splitlines() if ln.strip()][:2]
            for ln in lines:
                print("   •", ln)
        if r.get("steps"):
            first_step = r["steps"][0][:110] + ("..." if len(r["steps"][0]) > 110 else "")
            print("   Schritt 1:", first_step)
        print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Nutzung: py main.py "karotte, zwiebel"')
        sys.exit(0)
    query = sys.argv[1]
    results = plan(query, top_k=5, strict=True)
    pretty(results, query)
