# ui.py
import os
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")

st.set_page_config(page_title="Recipe Agent", page_icon="🍳", layout="wide")
st.title("🍳 Recipe Agent")
st.caption("Frag nach Rezepten basierend auf deinen Notion-Notizen – mit optionaler Anreicherung aus dem Web.")

# ---- Sidebar: Einstellungen ----
with st.sidebar:
    st.header("Einstellungen")
    api_base = st.text_input("API Base URL", value=API_BASE, help="FastAPI-Server (z. B. http://127.0.0.1:8000)")
    mode = st.radio("Modus", ["Chat (/chat)", "Direkt (/plan)"], index=0)
    top_k = st.slider("Top-K Ergebnisse", 1, 10, 5)
    strict = st.checkbox("Strenges Matching (alle Wörter müssen vorkommen)", value=True)
    excludes_text = st.text_input("Ohne diese Zutaten (kommagetrennt)", value="")
    use_llm = st.checkbox("LLM-Antwort aktivieren (OpenAI)", value=True)
    st.markdown("---")
    st.caption("Tipp: In deiner `.env` des Backends `ALLOW_WEB_ENRICHMENT=true` setzen, damit Lücken angereichert werden.")

# ---- Eingabe ----
query = st.text_input("🧺 Was hast du im Kühlschrank / worauf hast du Lust?")
submit = st.button("Vorschläge holen")

def call_chat(message: str, use_llm: bool):
    url = f"{api_base}/chat"
    return requests.post(url, json={"message": message, "use_llm": use_llm}, timeout=30).json()

def call_plan(pantry: str, excludes: list[str], top_k: int, strict: bool):
    url = f"{api_base}/plan"
    payload = {"pantry": pantry, "exclude": excludes, "top_k": top_k, "strict": strict}
    return requests.post(url, json=payload, timeout=45).json()

def build_shopping_list(items: list[dict]) -> list[str]:
    lines = []
    seen = set()
    for r in items or []:
        for ing in r.get("ingredients") or []:
            key = ing.strip().lower()
            if key and key not in seen:
                seen.add(key)
                lines.append(ing.strip())
    return lines

# ---- Run ----
if submit:
    if not query.strip():
        st.warning("Bitte gib eine Anfrage ein (z. B. „karotte, zwiebel“).")
    else:
        excludes = [x.strip() for x in excludes_text.split(",") if x.strip()]
        with st.spinner("Denke nach…"):
            try:
                if mode.startswith("Chat"):
                    if query:
                        data = call_chat(query, use_llm)
                    results = data.get("results", [])
                    reply = data.get("reply", "")
                else:
                    data = call_plan(query, excludes, top_k, strict)
                    results = data.get("items", [])
                    reply = f"Beste Vorschläge für: {data.get('query','')}"
            except Exception as e:
                st.error(f"API-Fehler: {e}")
                st.stop()

        st.subheader("Ergebnis")
        if reply:
            st.write(reply)

        if not results:
            st.info("Keine passenden Rezepte gefunden.")
        else:
            # Ergebnis-Karten
            for idx, r in enumerate(results, start=1):
                with st.container(border=True):
                    title = r.get("title", f"Rezept {idx}")
                    src = r.get("enrichment_source", "original")
                    score = r.get("score", 0)
                    st.markdown(f"**{idx}. {title}**  \n*Quelle:* `{src}` · *Score:* {score}")

                    ings = r.get("ingredients") or []
                    if ings:
                        st.markdown("**Zutaten:**")
                        st.markdown("\n".join(f"- {z}" for z in ings))

                    steps = r.get("steps") or []
                    if steps:
                        with st.expander("Zubereitung anzeigen"):
                            st.markdown("\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)))

            # Einkaufsliste aus den z. B. Top-3
            st.markdown("---")
            st.subheader("🛒 Einkaufsliste (aus den angezeigten Treffern)")
            shop = build_shopping_list(results)
            if shop:
                st.code("\n".join(f"- {x}" for x in shop), language=None)
            else:
                st.caption("Keine Zutaten gefunden oder alle Treffer ohne Zutaten.")

# Footer
st.markdown("---")
st.caption("Backend: FastAPI · Frontend: Streamlit · Datenquelle: Deine Notion-Seite + optionales Enrichment.")
