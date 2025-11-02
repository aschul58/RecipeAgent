import os
import requests
from dotenv import load_dotenv

# 1. Lade deine .env Datei
load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
PAGE_ID = os.getenv("NOTION_RECIPES_ID")

# 2. Setze Header für Notion API
headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28"
}

# 3. Endpoint zum Lesen der Inhalte deiner Seite
url = f"https://api.notion.com/v1/blocks/{PAGE_ID}/children?page_size=10"

# 4. Anfrage schicken
response = requests.get(url, headers=headers)

# 5. Ergebnis anzeigen
if response.status_code == 200:
    print("Connection successfull!")
    data = response.json()
    print(f"Es wurden {len(data.get('results', []))} Blöcke gefunden:\n")
    for block in data.get("results", []):
        print("-", block["type"])
else:
    print("Error:", response.status_code)
    print(response.text)
