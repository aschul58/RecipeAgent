# apps/ui/ui.py
import os
import requests
import streamlit as st

# --- Config & Secrets (safe) ---
try:
    _secrets = dict(st.secrets)
except Exception:
    _secrets = {}

API_BASE = os.getenv("API_BASE") or _secrets.get("API_BASE") or "http://127.0.0.1:8000"
API_KEY  = os.getenv("API_KEY")  or _secrets.get("API_KEY")  or ""
HEADERS  = {"X-API-Key": API_KEY} if API_KEY else {}

# --- Page setup ---
st.set_page_config(page_title="Recipe Agent", layout="wide")

# --- Minimal CSS for a "techy" dark look (no emojis) ---
st.markdown("""
<style>
/* overall spacing */
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
/* headline + subline */
h1 { letter-spacing: 0.2px; }
.subtitle {
  color: #a0a7b4; margin-top: -0.4rem; margin-bottom: 1.2rem;
  font-size: 0.98rem;
}
/* input panel */
.panel {
  background: #161a23;
  border: 1px solid #1f2430;
  border-radius: 12px;
  padding: 16px 16px 6px 16px;
}
/* result cards */
.card {
  background: #121620;
  border: 1px solid #242a36;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
}
.card h4 { margin: 0 0 6px 0; }
.card .meta { color: #9aa2af; font-size: 0.85rem; margin-bottom: 8px; }
.card ul, .card ol { margin: 0.3rem 0 0.2rem 1.2rem; }
hr.divider { border: none; border-top: 1px solid #202634; margin: 16px 0; }
footer { color: #808697; font-size: 0.85rem; margin-top: 8px; }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.title("Recipe Agent")
st.markdown('<div class="subtitle">Cook from your own recipes. A small agent that reads your Notion cookbook and suggests meals based on what you have.</div>', unsafe_allow_html=True)

# --- Sidebar: settings & diagnostics ---
with st.sidebar:
    st.header("Settings")
    use_llm = st.toggle("LLM answer (OpenAI)", value=False)
    top_k   = st.slider("Number of suggestions", 1, 10, 5)
    strict  = st.toggle("Strict ingredient matching", value=True)
    excludes_text = st.text_input("Exclude (comma-separated)", value="", help="Words/ingredients to avoid")
    st.caption(f"API_BASE = {API_BASE}")
    if st.button("Test /health"):
        try:
            r = requests.get(f"{API_BASE}/health", headers=HEADERS, timeout=10)
            st.success(f"/health → {r.status_code}: {r.text[:180]}")
        except Exception as e:
            st.error(f"Cannot reach API: {e}")

# --- Inputs ---
st.markdown('<div class="panel">', unsafe_allow_html=True)
col1, col2 = st.columns([3,1])
with col1:
    query = st.text_input("What do you have / what do you want to cook?", placeholder="e.g. carrots, onions, pasta")
with col2:
    mode  = st.selectbox("Mode", ["Chat (/chat)", "Direct (/plan)"])
go = st.button("Search")
st.markdown('</div>', unsafe_allow_html=True)

# --- HTTP helpers ---
def call_chat(message: str, use_llm: bool):
    url = f"{API_BASE}/chat"
    return requests.post(url, json={"message": message, "use_llm": use_llm}, headers=HEADERS, timeout=30).json()

def call_plan(pantry: str, excludes: list[str], top_k: int, strict: bool):
    url = f"{API_BASE}/plan"
    payload = {"pantry": pantry, "exclude": excludes, "top_k": top_k, "strict": strict}
    return requests.post(url, json=payload, headers=HEADERS, timeout=45).json()

# --- Action ---
if go:
    if not query.strip():
        st.warning("Please enter a query.")
    else:
        excludes = [x.strip() for x in excludes_text.split(",") if x.strip()]
        with st.spinner("Working..."):
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

        # Answer
        if reply:
            st.subheader("Answer")
            st.write(reply)

        # Results
        st.subheader("Results")
        if not results:
            st.info("No matching recipes found.")
        else:
            for i, r in enumerate(results, 1):
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown(f"<h4>{i}. {r.get('title','')}</h4>", unsafe_allow_html=True)
                meta = f"source: {r.get('enrichment_source','original')}"
                if "score" in r:
                    meta += f"  · score: {r.get('score',0)}"
                st.markdown(f'<div class="meta">{meta}</div>', unsafe_allow_html=True)

                if r.get("ingredients"):
                    st.markdown("**Ingredients:**")
                    st.markdown("\n".join(f"- {z}" for z in r["ingredients"]))

                if r.get("steps"):
                    with st.expander("Steps"):
                        st.markdown("\n".join(f"{k+1}. {s}" for k, s in enumerate(r["steps"])))

                st.markdown('</div>', unsafe_allow_html=True)

# --- Footer ---
st.markdown('<hr class="divider" />', unsafe_allow_html=True)
st.markdown('<footer>Tip: try queries like “I have carrots and onions” or “no feta”.</footer>', unsafe_allow_html=True)
