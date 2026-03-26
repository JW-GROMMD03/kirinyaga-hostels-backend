import requests
import os

BASE_URL = "http://127.0.0.1:8000/api/admin"
endpoints = ["/plans/", "/owner-subscriptions/", "/payments/"]

for ep in endpoints:
    url = BASE_URL + ep
    print(f"Testing {url} ...")
    try:
        r = requests.get(url)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print("Data:", r.json()[:100] if r.json() else "[]")
        else:
            print("Error:", r.text[:200])
    except Exception as e:
        print("Exception:", e)
    print("-" * 40)