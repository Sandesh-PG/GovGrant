"""Quick test for conversational fallback intake."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import requests
import json

BASE = "http://localhost:8000/api"

# Login
r = requests.post(f"{BASE}/auth/login", json={"email": "test@test.com", "password": "test123"})
token = r.json()["token"]
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Create session
sid = requests.post(f"{BASE}/sessions", headers=H).json()["session_id"]

print("=== MSG 1: Hello ===")
r1 = requests.post(f"{BASE}/chat", headers=H, json={"session_id": sid, "message": "Hello", "history": []}).json()
print(f"BOT: {r1['reply'][:200]}")
print(f"fields: {r1['fields_collected']}\n")

print("=== MSG 2: Rich intro ===")
hist = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Welcome"}]
r2 = requests.post(f"{BASE}/chat", headers=H, json={
    "session_id": sid,
    "message": "We are GreenLeaf Organics, a food processing startup in Pune, Maharashtra with 12 employees",
    "history": hist
}).json()
print(f"BOT: {r2['reply'][:300]}")
print(f"fields: {r2['fields_collected']}, complete: {r2['intake_complete']}\n")

print("=== MSG 3: Revenue + purpose ===")
hist2 = hist + [
    {"role": "user", "content": "We are GreenLeaf Organics, a food processing startup in Pune with 12 employees"},
    {"role": "assistant", "content": "Got it"}
]
r3 = requests.post(f"{BASE}/chat", headers=H, json={
    "session_id": sid,
    "message": "Revenue is about 80 lakhs and we need funding for machinery upgrade",
    "history": hist2
}).json()
print(f"BOT: {r3['reply'][:400]}")
print(f"fields: {r3['fields_collected']}, complete: {r3['intake_complete']}")
if r3.get("profile"):
    print(f"PROFILE: {json.dumps(r3['profile'], indent=2)}")
