from __future__ import annotations
import os
import requests
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

NOTION_VERSION = "2022-06-28"


def _get_env(name: str, required: bool = True, default: Optional[str] = None) -> Optional[str]:
    val = os.getenv(name, default)
    if required and not val:
        raise ValueError(f"Environment variable '{name}' is missing. "
                         f"Set it in your .env (e.g., {name}=...)")
    return val

def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

def fetch_blocks(page_id: Optional[str] = None, token: Optional[str] = None, page_size: int = 100) -> List[Dict[str, Any]]:
    """
    Lädt ALLE Blöcke einer Seite (paginiert). Gibt eine geordnete Liste von Block-Objekten zurück.
    """
    load_dotenv()
    page_id = page_id or _get_env("NOTION_RECIPES_ID")
    token = token or _get_env("NOTION_TOKEN")

    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = _headers(token)

    results: List[Dict[str, Any]] = []
    params = {"page_size": page_size}
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"Notion API error {resp.status_code}: {resp.text}")
        data = resp.json()
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        params["start_cursor"] = data.get("next_cursor")
    return results

def _rich_text_to_plain(rt_list: List[Dict[str, Any]]) -> str:
    # Fügt alle Plaintext-Segmente zusammen
    out = []
    for r in rt_list or []:
        if r.get("type") == "text":
            out.append(r["text"].get("content", ""))
        else:
            # Falls z. B. mention, equation … – nimm den plain_text fallback
            out.append(r.get("plain_text", ""))
    return "".join(out).strip()

def block_to_lines(block: Dict[str, Any]) -> List[str]:
    """
    Normalisiert einen Notion-Block in 0..n Klartext-Zeilen.
    - paragraph, quote → 1 Zeile
    - bulleted_list_item, numbered_list_item → "- " + Text
    - heading_1..3 → Überschrift (ohne '- ')
    - divider → spezielle Markierung: '---'
    - andere Typen → ignorieren (leer)
    """
    btype = block.get("type")
    data = block.get(btype, {}) if btype else {}

    if btype in ("paragraph", "quote"):
        text = _rich_text_to_plain(data.get("rich_text", []))
        return [text] if text else []

    if btype in ("bulleted_list_item", "numbered_list_item"):
        text = _rich_text_to_plain(data.get("rich_text", []))
        return [f"- {text}"] if text else []

    if btype in ("heading_1", "heading_2", "heading_3"):
        text = _rich_text_to_plain(data.get("rich_text", []))
        return [text] if text else []

    if btype == "divider":
        return ["---"]

    # Optional: weitere Typen (callout, toggle etc.) hier ergänzen
    return []

def blocks_to_text_lines(blocks: List[Dict[str, Any]]) -> List[str]:
    """
    Wandelt eine Blockliste in eine flache Liste von Textzeilen um.
    """
    lines: List[str] = []
    for b in blocks:
        for line in block_to_lines(b):
            if line is None:
                continue
            # Whitespace normalisieren
            s = line.strip()
            # Leere Zeilen vermeiden (außer Divider)
            if not s and s != "---":
                continue
            lines.append(s)
    return lines

def split_sections(lines: List[str]) -> List[List[str]]:
    """
    Teilt die Zeilen an '---' in Abschnitte.
    """
    sections: List[List[str]] = []
    current: List[str] = []
    for ln in lines:
        if ln == "---":
            if current:
                sections.append(current)
                current = []
        else:
            current.append(ln)
    if current:
        sections.append(current)
    return sections

def section_to_recipe(section_lines: List[str]) -> Optional[Dict[str, Any]]:
    """
    Wandelt einen Abschnitt in ein Rezept-Dict um:
      - title: erste nicht-leere Zeile (ohne führendes '- ')
      - body: restliche Zeilen als Text (mit \n)
      - lines: alle Zeilen (für Debug)
    Gibt None zurück, wenn kein sinnvoller Titel gefunden wird.
    """
    if not section_lines:
        return None

    # Titel = erste sinnvolle Zeile, die NICHT mit '- ' beginnt
    title = None
    for ln in section_lines:
        if ln and not ln.startswith("-"):
            title = ln.strip(": ").strip()
            break

    if not title:
        # Notfall: nimm die erste Zeile (auch wenn Bullet) und entferne das '- '
        first = section_lines[0]
        title = first[2:].strip() if first.startswith("- ") else first

    # Body = alle Zeilen ab der Zeile nach dem Titel
    started = False
    body_lines: List[str] = []
    for ln in section_lines:
        if not started and (ln == title or ln.rstrip(":") == title):
            started = True
            continue
        if started:
            body_lines.append(ln)

    body = "\n".join(body_lines).strip()
    if not title:
        return None

    return {"title": title, "body": body, "lines": section_lines}

def parse_recipes_from_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Pipeline
    """
    lines = blocks_to_text_lines(blocks)
    sections = split_sections(lines)
    recipes: List[Dict[str, Any]] = []
    for sec in sections:
        r = section_to_recipe(sec)
        if r and (r["title"] or r["body"]):
            recipes.append(r)
    return recipes


def get_recipes(page_id: Optional[str] = None, token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Liest Rezepte aus meiner Notion-Seite:
    - lädt alle Blocks,
    - splittet an Divider,
    - gibt Liste von Rezept-Dicts zurück.
    """
    blocks = fetch_blocks(page_id=page_id, token=token)
    return parse_recipes_from_blocks(blocks)

if __name__ == "__main__":
    load_dotenv()
    recipes = get_recipes()
    print(f"Success! {len(recipes)} Rezepte gefunden\n")
    for r in recipes:
        print("—", r["title"])
        # kurze Vorschau
        if r["body"]:
            preview = r["body"].splitlines()[:3]
            for line in preview:
                print("   ", line)
        print()