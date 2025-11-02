# enrichment.py
# -------------------------------------------
# Enrichment-Pipeline für unvollständige Rezepte.
# - Heuristik: completeness check
# - Optionaler Lookup: Spoonacular (API) oder Web-Suche (Platzhalter)
# - Caching in JSON
# - Merge ohne Original zu überschreiben
#
# .env Beispiel:
#   ALLOW_WEB_ENRICHMENT=true
#   ENRICH_DEBUG=1
#   SPOONACULAR_API_KEY=...
#   # optional:
#   OPENAI_API_KEY=...
# -------------------------------------------

from __future__ import annotations
import os, json, time, re
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

CACHE_PATH = "enrichment_cache.json"

# ----------------- Debug -----------------

def _dbg(*args):
    # liest jedes Mal dynamisch, damit du nicht neu importieren musst
    if os.getenv("ENRICH_DEBUG", "0") in ("1", "true", "True"):
        print("[ENRICH]", *args)

# ----------------- Cache -----------------

def _load_cache() -> Dict[str, Any]:
    if os.path.exists(CACHE_PATH):
        try:
            return json.load(open(CACHE_PATH, "r", encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save_cache(cache: Dict[str, Any]) -> None:
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CACHE_PATH)

def _cache_key(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())

# ----------------- Completeness Heuristik -----------------

_COOKING_HINTS = [
    "zutaten", " g", " ml", " el", " tl", "koch", "anbrat", "back", "min", "ofen",
    "pfanne", "topf", "wasser", "öl", "brüh", "würfel", "misch", "rühr", "reduzier"
]

def assess_completeness(recipe: Dict[str, Any]) -> Dict[str, Any]:
    """Sehr einfache Heuristik: genug Inhalt vorhanden?"""
    title = (recipe.get("title") or "").strip()
    body  = (recipe.get("body") or "").strip()
    if not title:
        return {"is_complete": False, "reason": "kein Titel"}

    lines = [ln for ln in body.splitlines() if ln.strip()]
    enough_lines = len(lines) >= 3

    lower = body.lower()
    has_cooking_terms = any(h in lower for h in _COOKING_HINTS)

    is_complete = bool(enough_lines or has_cooking_terms)
    reason = "ok" if is_complete else "zu wenig Struktur/Text"
    return {"is_complete": is_complete, "reason": reason}

# ----------------- Enrichment Provider -----------------

def _enrich_via_spoonacular(title: str) -> Optional[Dict[str, Any]]:
    """
    Robuster Spoonacular-Provider:
    1) complexSearch (findet id)
    2) recipes/{id}/information (holt details)
    + Fallback: plain 'instructions' in Sätze splitten
    + DE→EN Titel-Fallback (gulasch -> goulash)
    """
    key = os.getenv("SPOONACULAR_API_KEY")
    if not key:
        _dbg("Kein SPOONACULAR_API_KEY gesetzt.")
        return None

    import requests

    def _search_id(q: str) -> Optional[int]:
        url = "https://api.spoonacular.com/recipes/complexSearch"
        params = {"apiKey": key, "query": q, "number": 1}
        r = requests.get(url, params=params, timeout=30)
        _dbg("Spoonacular search status:", r.status_code, "query=", q)
        if r.status_code != 200:
            _dbg("Spoonacular search error:", r.text[:200])
            return None
        data = r.json()
        if not data.get("results"):
            return None
        return data["results"][0].get("id")

    def _strip_html(x: str) -> str:
        return re.sub(r"<[^>]+>", "", x or "").strip()

    def _fetch_info(recipe_id: int) -> Optional[Dict[str, Any]]:
        url = f"https://api.spoonacular.com/recipes/{recipe_id}/information"
        params = {"apiKey": key, "includeNutrition": False}
        r = requests.get(url, params=params, timeout=30)
        _dbg("Spoonacular info status:", r.status_code, "id=", recipe_id)
        if r.status_code != 200:
            _dbg("Spoonacular info error:", r.text[:200])
            return None
        data = r.json()

        ingredients = [i["original"] for i in data.get("extendedIngredients", []) if i.get("original")]

        steps: List[str] = []
        for a in (data.get("analyzedInstructions") or []):
            for s in (a.get("steps") or []):
                if s.get("step"):
                    steps.append(s["step"])

        # Fallback: plain instructions (HTML -> Text -> grob in Sätze)
        if not steps:
            instr = _strip_html(data.get("instructions") or "")
            if instr:
                parts = re.split(r"[.\n]+", instr)
                steps = [p.strip() for p in parts if len(p.strip()) > 3][:12]

        if not ingredients and not steps:
            return None

        return {
            "ingredients": ingredients or [],
            "steps": steps or [],
            "source": f"api:spoonacular:{recipe_id}",
            "fetched_at": int(time.time())
        }

    # 1) direkter Suchversuch
    rid = _search_id(title.strip())

    # 2) DE→EN-Fallback, falls nötig
    if not rid:
        de = title.strip().lower()
        de_ascii = (de
                    .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss"))
        synonyms = {
            "gulasch": "goulash",
            "zwiebelsuppe": "onion soup",
            "pfannkuchen": "pancakes",
            "käsespätzle": "cheese spaetzle",
            "kase spaetzle": "cheese spaetzle",
        }
        candidate = synonyms.get(de, de_ascii)
        if candidate != de:
            rid = _search_id(candidate)

    if not rid:
        _dbg("Keine recipe-id gefunden.")
        return None

    return _fetch_info(rid)

def _enrich_via_websearch(title: str) -> Optional[Dict[str, Any]]:
    """
    Platzhalter für Websuche (z. B. Bing/SerpAPI).
    Hier bewusst leer gelassen; kann später ergänzt werden.
    """
    key = os.getenv("BING_SEARCH_API_KEY")
    if not key:
        return None
    # TODO: Implementiere Websuche → HTML holen → per LLM Zutaten/Steps extrahieren
    return None

def _enrich_via_llm_generic(title: str) -> Optional[Dict[str, Any]]:
    """
    Letzter Fallback: generisches LLM bittet um plausible Zutaten/Schritte.
    Kennzeichne Quelle klar als 'llm:generic'.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = (
            "Erzeuge eine plausible Zutatenliste und 6-8 Kochschritte für das Rezept: "
            f"'{title}'. Antworte als kompaktes JSON mit den Feldern "
            "'ingredients' (List of strings) und 'steps' (List of strings). "
            "Keine Erklärtexte."
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        data = resp.choices[0].message.parsed or {}
        ingredients = data.get("ingredients", [])
        steps = data.get("steps", [])
        if not ingredients and not steps:
            return None
        return {
            "ingredients": ingredients,
            "steps": steps,
            "source": "llm:generic",
            "fetched_at": int(time.time())
        }
    except Exception as e:
        _dbg("LLM-Fallback Fehler:", e)
        return None

# ----------------- Orchestrierung -----------------

def enrich_recipe(title: str) -> Optional[Dict[str, Any]]:
    """Versucht Anreicherung via Provider in Reihenfolge. Nutzt Cache."""
    load_dotenv()
    _dbg("ALLOW_WEB_ENRICHMENT=", os.getenv("ALLOW_WEB_ENRICHMENT"))
    _dbg("SPOONACULAR_API_KEY set? ", bool(os.getenv("SPOONACULAR_API_KEY")))

    if os.getenv("ALLOW_WEB_ENRICHMENT", "false").lower() not in ("true", "1", "yes"):
        _dbg("Enrichment deaktiviert (ALLOW_WEB_ENRICHMENT != true).")
        return None

    cache = _load_cache()
    key = _cache_key(title)
    if key in cache:
        _dbg("Cache hit:", title)
        return cache[key]

    # Provider-Reihenfolge: API → Web → LLM (optional)
    for provider in (_enrich_via_spoonacular, _enrich_via_websearch, _enrich_via_llm_generic):
        try:
            enriched = provider(title)
        except Exception as e:
            _dbg("Provider-Fehler:", provider.__name__, e)
            enriched = None
        if enriched:
            cache[key] = enriched
            _save_cache(cache)
            _dbg("Enrichment erfolgreich via", enriched.get("source"))
            return enriched

    _dbg("Keine Anreicherung gefunden.")
    return None

# ----------------- Merge-Logik -----------------

def merge_recipe(recipe: Dict[str, Any], enriched: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Non-destructive Merge: nutzt Enrichment nur, wenn im Original nichts da ist."""
    out = dict(recipe)
    body = (recipe.get("body") or "")
    orig_lines = [ln.strip("- ").strip() for ln in body.splitlines() if ln.strip()]

    # Zutaten/Steps aus Original heuristisch ableiten
    unit_clues = (" g", " ml", " el", " tl", " stück", "stk", "dose", " prise", "tasse")
    verb_clues = ("brat", "koch", "back", "schneid", "rühr", "misch", "aufkoch", "reduzier", "würz", "gar")
    orig_ingredients = [ln for ln in orig_lines if any(u in ln.lower() for u in unit_clues)]
    orig_steps = [ln for ln in orig_lines if any(v in ln.lower() for v in verb_clues)]

    ingredients = orig_ingredients or (enriched.get("ingredients") if enriched else [])
    steps = orig_steps or (enriched.get("steps") if enriched else [])

    out["ingredients"] = ingredients
    out["steps"] = steps
    if enriched:
        out["enrichment_source"] = enriched.get("source")
        out["enriched_at"] = enriched.get("fetched_at")
    return out

def enrich_if_needed(recipe: Dict[str, Any]) -> Dict[str, Any]:
    """Prüft Vollständigkeit, reichert bei Bedarf an, merged das Ergebnis."""
    info = assess_completeness(recipe)
    _dbg("Completeness:", recipe.get("title"), info)
    if info["is_complete"]:
        return merge_recipe(recipe, None)
    enriched = enrich_recipe(recipe.get("title", ""))
    return merge_recipe(recipe, enriched)

# ----------------- Mini-CLI zum schnellen Test -----------------

if __name__ == "__main__":
    load_dotenv()
    os.environ.setdefault("ENRICH_DEBUG", "1")  # CLI-Tests: Debug an
    
