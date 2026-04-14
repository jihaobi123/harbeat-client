import requests, json
r = requests.post("http://localhost:8000/api/recommendations/vibe-search", json={"query":"rainy night driving","top_k":5})
print(json.dumps(r.json(), indent=2, ensure_ascii=False))
