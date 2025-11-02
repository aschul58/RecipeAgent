from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()  # lädt .env
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

print("API-Key geladen?", bool(os.getenv("OPENAI_API_KEY")))

try:
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": "Sag mir ein schnelles vegetarisches Gericht mit Karotten."}],
    )
    print("\n--- OpenAI Response ---")
    print(response.choices[0].message.content)
except Exception as e:
    print("Fehler:", e)
