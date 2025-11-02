import types
from recipe_agent import agent as ag

def _stub_candidates():
    # Minimal, deterministic “recipes” as search results
    return [
        {"title": "Pasta Feta", "body": "", "ingredients": ["pasta", "feta", "olive oil"]},
        {"title": "Carrot Tofu Stir Fry", "body": "", "ingredients": ["carrot", "tofu", "soy sauce"]},
        {"title": "Potato Soup", "body": "", "ingredients": ["potato", "onion", "cream"]},
        {"title": "Tomato Salad", "body": "", "ingredients": ["tomato", "feta", "olive oil"]},
    ]

def _fake_search_recipes(pantry_query, recipes=None, must_include_all=True, top_k=12):
    # Very simple matcher: include all tokens if strict, else any token
    toks = [t for t in ag.tokenize(pantry_query) if len(t) > 1]
    res = []
    for r in _stub_candidates():
        ings = set(i.lower() for i in r["ingredients"])
        ok = (set(toks).issubset(ings)) if must_include_all else (bool(set(toks) & ings))
        if ok:
            res.append({"title": r["title"], "body": ""})
    return res[:top_k]

def _fake_enrich_if_needed(recipe):
    # Pass-through enrichment: attach our deterministic “ingredients”
    for r in _stub_candidates():
        if r["title"] == recipe["title"]:
            return {
                "title": r["title"],
                "ingredients": r["ingredients"],
                "steps": [],
                "body": "",
                "enrichment_source": "original",
            }
    return {"title": recipe["title"], "ingredients": [], "steps": [], "body": ""}

def setup_module(_module):
    # Monkeypatch inside the imported module namespace
    ag.search_recipes = _fake_search_recipes
    ag.enrich_if_needed = _fake_enrich_if_needed

def test_tool_plan_excludes_terms():
    out = ag.tool_plan("tomato feta", top_k=5, strict=False, exclude=["feta"])
    titles = [x["title"] for x in out]
    # Items containing 'feta' anywhere in title/ingredients should be filtered out
    assert "Tomato Salad" not in titles
    assert "Pasta Feta" not in titles

def test_tool_plan_strict_vs_loose():
    # strict=True requires ALL tokens present
    strict_out = ag.tool_plan("carrot tofu", top_k=5, strict=True)
    strict_titles = [x["title"] for x in strict_out]
    assert "Carrot Tofu Stir Fry" in strict_titles
    # strict=False allows ANY token; should include items that match only one
    loose_out = ag.tool_plan("carrot tofu", top_k=5, strict=False)
    loose_titles = [x["title"] for x in loose_out]
    assert "Carrot Tofu Stir Fry" in loose_titles
    # With loose match, more items can appear (e.g., those with just 'tofu' or just 'carrot')
    assert len(loose_titles) >= len(strict_titles)

def test_tool_plan_topk():
    out = ag.tool_plan("tomato", top_k=1, strict=False)
    assert len(out) == 1
