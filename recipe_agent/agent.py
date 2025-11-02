# agent.py
# ------------------------------------------------------------
# Leichter CLI-Agent ohne LLM:
# - Intent-Routing (plan/substitute/scale/shopping_list/save)
# - Tool-Wrappers auf bestehende Module
# - Einfache Entities (pantry, exclude, persons) aus der Nutzerfrage
# - Interaktive CLI (optional) oder Einmalaufruf mit Argument
# ------------------------------------------------------------

from __future__ import annotations
import re
import sys
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv
from recipe_agent.query_recipes import search_recipes
from recipe_agent.enrichment import enrich_if_needed
from recipe_agent.notion_api import get_recipes
from recipe_agent.llm_answer import format_plan_with_llm

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("recipe-agent")

load_dotenv()

WORD_RX = re.compile(r"[A-Za-zÄÖÜäöüß0-9]+", re.IGNORECASE)

# ------------------------ Utilities ------------------------

def tokenize(text: str) -> List[str]:
    return [w.lower() for w in WORD_RX.findall(text or "")]

def dedup_keep_order(xs: List[str]) -> List[str]:
    seen = set(); out = []
    for x in xs:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def extract_entities(message: str) -> Dict[str, Any]:
    """
    Holt aus der Frage:
    - pantry: Zutaten (einfach alle Substantive/Wörter; später durch Stopwörter verfeinern)
    - exclude: 'ohne feta', 'keine milch'
    - persons: 'für 5 personen/portionen'
    """
    msg = message.lower()

    # persons
    m = re.search(r"f(?:ür|uer)\s*(\d+)\s*(?:personen?|portion(?:en)?)", msg)
    persons = int(m.group(1)) if m else None

    # exclude (ohne/keine X)
    exclude = []
    for pat in re.findall(r"(?:ohne|keine|kein)\s+([a-zäöüß\- ]+)", msg):
        exclude += [w.strip() for w in tokenize(pat)]
    exclude = dedup_keep_order([w for w in exclude if len(w) > 1])

    # pantry (einfach: alle Tokens minus Stoppwörter & exclude-Trigger)
    stops = set([
        "ich","habe","hab","und","oder","mit","ohne","kein","keine","bitte","was",
        "kann","kochen","essen","gericht","rezept","für","person","personen","portion","portionen",
        "machen","schnell","heute","abend","mittag","plan","woche","tage","tage?", "tage."
    ])
    pantry = [w for w in tokenize(msg) if w not in stops]
    # Nimm als Pantry nur Lebensmittel-ähnliches (grob: mind. 3 Zeichen, kein Zahlwort)
    pantry = [w for w in pantry if len(w) >= 3 and not w.isdigit()]
    # entferne Wörter aus exclude
    pantry = [w for w in pantry if w not in exclude]

    return {"pantry": dedup_keep_order(pantry), "exclude": exclude, "persons": persons}

# ------------------------ Intent Router ------------------------

def route_intent(message: str) -> str:
    m = message.lower()
    if any(k in m for k in ["einkaufsliste", "shopping", "liste erstellen", "liste machen"]):
        return "shopping_list"
    if any(k in m for k in ["ersetzen", "substitute", "alternative", "ohne "]):
        return "substitute"
    if re.search(r"f(?:ür|uer)\s*\d+\s*(?:personen?|portion(?:en)?)", m):
        return "scale"
    if any(k in m for k in ["plan", "meal", "woche", "tage", "abendessen"]):
        return "plan"
    # Default: plan über Pantry
    return "plan"

# ------------------------ Tools ------------------------

def tool_plan(
    pantry_query: str,
    top_k: int = 5,
    strict: bool = True,
    exclude: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Rank recipes against `pantry_query`.
    `exclude` is a list of words/ingredients to filter out (case-insensitive substring).
    """

    pre = search_recipes(pantry_query, recipes=None, must_include_all=strict, top_k=12)
    pantry_tokens = dedup_keep_order([w for w in tokenize(pantry_query) if len(w) > 1])

    out: List[Dict[str, Any]] = []
    for item in pre:
        merged = enrich_if_needed({"title": item["title"], "body": item.get("body", "")})
        score = rescoring_by_ingredients(merged, pantry_tokens)
        out.append({
            "title": merged.get("title"),
            "ingredients": merged.get("ingredients", []),
            "steps": merged.get("steps", []),
            "body": merged.get("body", ""),
            "enrichment_source": merged.get("enrichment_source", "original"),
            "score": score,
        })

    # sort by score descending
    out.sort(key=lambda x: x["score"], reverse=True)

    # apply exclude filter (if any)
    excl = {x.strip().lower() for x in (exclude or []) if x and x.strip()}
    if excl:
        def _contains_excluded(rec: Dict[str, Any]) -> bool:
            title = (rec.get("title") or "").lower()
            ingreds = " ".join(rec.get("ingredients") or []).lower()
            haystack = f"{title} {ingreds}"
            return any(term in haystack for term in excl)
        out = [r for r in out if not _contains_excluded(r)]

    return out[:top_k]

def rescoring_by_ingredients(merged_recipe: Dict[str, Any], pantry_tokens: List[str]) -> int:
    ingr = " ".join(merged_recipe.get("ingredients") or []).lower()
    body = (merged_recipe.get("body") or "").lower()
    hits_ing = sum(1 for t in pantry_tokens if t in ingr)
    hits_body = sum(1 for t in pantry_tokens if t in body)
    score = hits_ing * 3 + hits_body * 1
    if hits_ing >= 2:
        score += 2
    return score

def tool_substitute(recipe_title: str, missing_or_excluded: List[str]) -> Dict[str, Any]:
    """
    Heuristische Ersatzvorschläge (Kochlogik light).
    """
    # Mini-Wissensbasis
    subs = {
        "feta": ["ziegenkäse", "halloumi", "gesalzener hirtenkäse", "gewürzter tofu"],
        "milch": ["haferdrink", "mandelmilch", "sojadrink", "verdünnte sahne"],
        "sahne": ["creme fraiche", "schmand", "milch+butter", "kokosmilch"],
        "ei": ["leinsamen+wasser", "apfelmus", "banane (süß)"],
        "butter": ["öl+etwas margarine", "butterschmalz", "kokosöl (süß)"],
        "zwiebel": ["frühlingszwiebel", "schalotte", "porree"],
        "knoblauch": ["knoblauchpulver", "bärlauch", "asafoetida (indisch, sparsam)"],
        "fischsoße": ["sojasoße + anchovy paste minimal", "maggi (sparsam)", "miso + wasser"]
    }
    ideas = {}
    for miss in missing_or_excluded:
        m = miss.lower()
        # nächster Match
        key = next((k for k in subs.keys() if k in m), None)
        if key:
            ideas[key] = subs[key]
        else:
            ideas[m] = ["ähnliches profil via paprika/umami", "mehr salz/säure zur balance"]
    return {"title": recipe_title, "substitutions": ideas}

def tool_scale(ingredients: List[str], persons_from: Optional[int], persons_to: int) -> List[str]:
    """
    Skaliert einfache Mengenangaben grob hoch/runter.
    Erkennt Zahlen (Ganz/Dezimal) + Standard-Einheiten; ersetzt im String.
    """
    if not ingredients:
        return []
    factor = persons_to / float(persons_from or persons_to)
    def scale_line(line: str) -> str:
        def repl(m):
            num = m.group(1).replace(",", ".")
            try:
                val = float(num) * factor
                # schöne Ausgabe
                if abs(val - round(val)) < 1e-6:
                    s = f"{int(round(val))}"
                else:
                    s = f"{val:.1f}".rstrip("0").rstrip(".")
                return s + (m.group(2) or "")
            except Exception:
                return m.group(0)
        # z.B. "200g", "200 g", "1.5 EL", "1,5EL"
        return re.sub(r"(\d+(?:[.,]\d+)?)(\s?(?:g|ml|l|el|tl|kg|stk|stück)?)", repl, line, flags=re.IGNORECASE)
    return [scale_line(x) for x in ingredients]

def tool_shopping_list(recipes: List[Dict[str, Any]]) -> List[str]:
    """
    Konsolidiert Zutaten (simple Merge; keine Einheiten-Normalisierung).
    """
    items = []
    for r in recipes:
        for ing in (r.get("ingredients") or []):
            t = ing.strip()
            if t:
                items.append(t)
    # Grobe Deduplikation (case-insensitive)
    seen = set(); out = []
    for it in items:
        key = it.lower()
        if key not in seen:
            seen.add(key); out.append(it)
    return out

# ------------------------ Antwort-Formatter ------------------------

def format_plan_answer(results: List[Dict[str, Any]], query: str) -> str:
    if not results:
        return f"Keine passenden Rezepte für: {query}"
    lines = [f"Beste Vorschläge für: {query}\n"]
    for i, r in enumerate(results, 1):
        src = r.get("enrichment_source","original")
        lines.append(f"{i}. {r['title']}  (quelle: {src}, score: {r['score']})")
        if r.get("ingredients"):
            ing_preview = ", ".join(r["ingredients"][:6])
            suffix = " ..." if len(r["ingredients"]) > 6 else ""
            lines.append(f"   Zutaten: {ing_preview}{suffix}")
        elif r.get("body"):
            preview = [ln for ln in r["body"].splitlines() if ln.strip()][:2]
            for ln in preview:
                lines.append(f"   • {ln}")
    return "\n".join(lines)

# ------------------------ Agent Core ------------------------

def handle(message: str, context: dict | None = None, use_llm: bool = False) -> Dict[str, Any]:
    intent = route_intent(message)
    ents = extract_entities(message)

    if intent == "plan":
        strict = len(ents["pantry"]) >= 2
        q = " ".join(ents["pantry"]) if ents["pantry"] else message
        results = tool_plan(q, top_k=5, strict=strict, exclude=ents.get("exclude") or [])
        if use_llm and results:
            reply = format_plan_with_llm(message, results)
        else:
            reply = format_plan_answer(results, q)
        suggestions = []
        if results:
            suggestions = ["Einkaufsliste erstellen", "Mengen für 4 Personen", "Ohne Feta"]
            if results[0]["score"] < 3:
                suggestions.append("Weitere Zutat angeben")
        return {"intent": intent, "reply": reply, "results": results, "suggestions": suggestions}


    if intent == "substitute":
        # Nimm das Top-Ergebnis eines neutralen Plans als Referenz
        base = tool_plan(" ".join(ents["pantry"]) or "", top_k=1, strict=False)
        title = base[0]["title"] if base else "dein Rezept"
        sub = tool_substitute(title, ents["exclude"] or ents["pantry"])
        reply_lines = [f"Ersatzvorschläge für **{sub['title']}**:"]
        for k, vals in sub["substitutions"].items():
            reply_lines.append(f"- {k}: " + ", ".join(vals))
        return {"intent": intent, "reply": "\n".join(reply_lines), "substitutions": sub}

    if intent == "scale":
        # Hole Top-1 passend zu Pantry (falls genannt); sonst alle Rezepte und nimm erstes
        base = tool_plan(" ".join(ents["pantry"]) or "", top_k=1, strict=False)
        if not base:
            # als Fallback irgendein Rezept
            recs = get_recipes()
            if not recs:
                return {"intent": intent, "reply": "Keine Rezepte gefunden."}
            merged = enrich_if_needed(recs[0])
        else:
            merged = base[0]
        persons_to = ents["persons"] or 2
        scaled = tool_scale(merged.get("ingredients", []), persons_from=None, persons_to=persons_to)
        title = merged.get("title", "Rezept")
        reply = f"Skalierte Zutaten für **{title}** (≈ {persons_to} Personen):\n- " + "\n- ".join(scaled[:20])
        return {"intent": intent, "reply": reply, "ingredients_scaled": scaled}

    if intent == "shopping_list":
        # Nimm Top-3 aus einem Plan auf Basis der Pantry
        q = " ".join(ents["pantry"]) or ""
        results = tool_plan(q, top_k=3, strict=False)
        lst = tool_shopping_list(results)
        reply = "Einkaufsliste (konsolidiert):\n- " + "\n- ".join(lst[:40])
        return {"intent": intent, "reply": reply, "shopping_list": lst, "from": [r["title"] for r in results]}

    # optional: save stub
    if intent == "save":
        return {"intent": intent, "reply": "Speichern in Notion ist noch nicht verdrahtet (Stub)."}

    # Fallback
    return {"intent": "unknown", "reply": "Ich bin unsicher, was du brauchst. Versuch: 'ich habe karotte und zwiebel' oder 'ohne feta' oder 'für 5 personen'."}

# ------------------------ CLI ------------------------

def _cli_once(args: List[str]):
    msg = " ".join(args) if args else "ich habe karotte und zwiebel"
    out = handle(msg)
    print(out["reply"])
    if out.get("suggestions"):
        print("\nVorschläge:", ", ".join(out["suggestions"]))

def _cli_chat():
    print("Recipe Agent – tippe 'exit' zum Beenden.")

    start = time.time()
    out = handle(req.message, use_llm=bool(req.use_llm))
    logger.info({"route": "chat", "latency_ms": int((time.time()-start)*1000),
             "use_llm": bool(req.use_llm), "result_count": len(out.get("results") or [])})

    while True:
        try:
            msg = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not msg or msg.lower() in ("exit","quit"):
            break
        out = handle(msg)
        print(out["reply"])
        if out.get("suggestions"):
            print("\nVorschläge:", ", ".join(out["suggestions"]))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        _cli_once(sys.argv[1:])
    else:
        _cli_chat()
