from recipe_agent.enrichment import merge_recipe

def test_merge_prefers_original_when_present():
    original = {
        "title": "Pancakes",
        "body": "200 g flour\n1 tsp sugar\nMix and fry\n",
    }
    enriched = {
        "ingredients": ["flour", "milk", "eggs"],
        "steps": ["Mix all", "Fry"],
        "source": "api:stub:123",
    }
    merged = merge_recipe(original, enriched)

    # Heuristic should extract ingredients/steps from body → prefer original over enrichment
    assert merged["ingredients"], "Expected ingredients derived from original body"
    assert merged["steps"], "Expected steps derived from original body"
    # Enrichment source should still be recorded if provided
    assert merged.get("enrichment_source") == "api:stub:123"

def test_merge_uses_enrichment_if_original_empty():
    original = {"title": "Mystery Dish", "body": ""}
    enriched = {
        "ingredients": ["thing1", "thing2"],
        "steps": ["do A", "do B"],
        "source": "api:stub:999",
    }
    merged = merge_recipe(original, enriched)
    assert merged["ingredients"] == ["thing1", "thing2"]
    assert merged["steps"] == ["do A", "do B"]
    assert merged.get("enrichment_source") == "api:stub:999"
