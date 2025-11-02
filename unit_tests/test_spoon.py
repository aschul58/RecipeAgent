import os, requests
from dotenv import load_dotenv
load_dotenv()
key = os.getenv("SPOONACULAR_API_KEY")
print("Key set? ", bool(key))
url = "https://api.spoonacular.com/recipes/complexSearch"
params = {"apiKey": key, "query": "Spaghetti Bolognese", "number": 1, "addRecipeInformation": True}
r = requests.get(url, params=params, timeout=30)
print("Status:", r.status_code)
print("Body preview:", r.text[:300])
