# apps/ui/ui.py
import os
import requests
import streamlit as st

# Safely read secrets if present; otherwise fall back to env/defaults
try:
    _secrets = dict(st.secrets)
except Exception:
    _secrets = {}

API_BASE = os.getenv("API_BASE") or _secrets.get("API_BASE") or "http://127.0.0.1:8000"
API_KEY  = os.getenv("API_KEY")  or _secrets.get("API_KEY")  or ""
HEADERS  = {"X-API-Key": API_KEY} if API_KEY else {}

st.set_page_config(page_title="Recipe Agent", layout="wide")
st.title("Recipe Agent")

with st.sidebar:
    st.header("Settings")
    use_llm = st.checkbox("LLM answer (OpenAI)", value=False)
    top_k   = st.slider("Top-K", 1, 10, 5)
    strict  = st.checkbox("Strict matching", value=True)
    excludes_text = st.text_input("Exclude (comma-separated)", value="")
    st.caption(f"API: {API_BASE}")

query = st.text_input("What do you have / what do you want to cook?")
mode  = st.radio("Mode", ["Chat (/chat)", "Direct (/plan)"], index=0, horizontal=True)
go    = st.button("Search")

def call_chat(message: str, use_llm: bool):
    url = f"{API_BASE}/chat"
    return requests.post(url, json={"message": message, "use_llm": use_llm}, headers=HEADERS, timeout=30).json()

def call_plan(pantry: str, excludes: list[str], top_k: int, strict: bool):
    url = f"{API_BASE}/plan"
    payload = {"pantry": pantry, "exclude": excludes, "top_k": top_k, "strict": strict}
    return requests.post(url, json=payload, headers=HEADERS, timeout=45).json()

if go:
    if not query.strip():
        st.warning("Please enter a query.")
    else:
        excludes = [x.strip() for x in excludes_text.split(",") if x.strip()]
        with st.spinner("Thinking..."):
            try:
                if mode.startswith("Chat"):
                    data = call_chat(query, use_llm)
                    reply = data.get("reply", "")
                    results = data.get("results", [])
                else:
                    data = call_plan(query, excludes, top_k, strict)
                    reply = f"Best matches for: {data.get('query','')}"
                    results = data.get("items", [])
            except Exception as e:
                st.error(f"API error: {e}")
                st.stop()

        if reply:
            st.subheader("Answer")
            st.write(reply)

        st.subheader("Results")
        if not results:
            st.info("No matching recipes.")
        else:
            for i, r in enumerate(results, 1):
                with st.container():
                    st.markdown(f"**{i}. {r.get('title','')}**  · source: `{r.get('enrichment_source','original')}`  · score: {r.get('score',0)}")
                    if r.get("ingredients"):
                        st.markdown("**Ingredients:**")
                        st.markdown("\n".join(f"- {z}" for z in r["ingredients"]))
                    if r.get("steps"):
                        with st.expander("Steps"):
                            st.markdown("\n".join(f"{k+1}. {s}" for k, s in enumerate(r["steps"])))
