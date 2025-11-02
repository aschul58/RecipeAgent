from __future__ import annotations
import sys
import re
from typing import List, Dict, Any, Tuple
from recipe_agent.notion_api import get_recipes

WORD_RX = re.compile(r"[A-Za-zÄÖÜäöüß0-9]+")

def normalize(text: str) -> str:
    return text.lower()

def tokenize(text: str) -> List[str]:
    return [w.lower() for w in WORD_RX.findall(text or "")]

def score_recipe(recipe: Dict[str, Any], want: List[str]) -> Tuple[int, int]:
    """
    Gibt (hits_total, hits_in_title) zurück.
    - hits_total: wie viele gewünschte Tokens in title+body gefunden wurden
    - hits_in_title: Bonus, wenn Treffer im Titel vorkommen
    """
    title = normalize(recipe["title"])
    body  = normalize(recipe.get("body", ""))

    hits_total = 0
    hits_title = 0
    for w in want:
        in_title = w in title
        in_body  = w in body
        if in_title or in_body:
            hits_total += 1
            if in_title:
                hits_title += 1
    return hits_total, hits_title

def search_recipes(
    query: str,
    recipes: List[Dict[str, Any]] | None = None,
    must_include_all: bool = True,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Sucht Rezepte, die zu den gewünschten Wörtern passen.
    - must_include_all=True: nur Rezepte, die *alle* Wörter enthalten
      (strenger, gut für "ich habe Karotte UND Zwiebel").
    - must_include_all=False: erlaubt Teiltreffer, sortiert nach Score.

    Rückgabe: Liste von Dicts mit title, body, score.
    """
    if recipes is None:
        recipes = get_recipes()

    want = [w for w in tokenize(query) if len(w) > 1]
    if not want:
        return []

    scored = []
    for r in recipes:
        hits_total, hits_title = score_recipe(r, want)
        if must_include_all and hits_total < len(want):
            continue
        # einfacher Ranking-Score: Treffer + leichter Bonus für Titel-Treffer
        score = hits_total * 10 + hits_title * 2
        if score > 0:
            scored.append({"title": r["title"], "body": r.get("body",""), "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]

def pretty_print(results: List[Dict[str, Any]]):
    if not results:
        print("Keine passenden Rezepte gefunden.")
        return
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}  (score={r['score']})")
        # kurze Vorschau
        lines = (r["body"] or "").splitlines()
        preview = [ln for ln in lines if ln.strip()][:3]
        for ln in preview:
            print("   •", ln)
        print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Nutzung: py query_recipes.py \"karotte, zwiebel\"")
        sys.exit(0)
    query = sys.argv[1]
    results = search_recipes(query, must_include_all=True, top_k=5)
    pretty_print(results)