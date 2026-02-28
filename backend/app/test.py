# import websocket
# import json
# import threading
# from dhanhq_api import DhanHQAPI
# import pandas as pd


# client_id = "1109121898"
# access_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJwX2lwIjoiIiwic19pcCI6IiIsImlzcyI6ImRoYW4iLCJwYXJ0bmVySWQiOiIiLCJleHAiOjE3NjI3NzgxMzUsImlhdCI6MTc2MjY5MTczNSwidG9rZW5Db25zdW1lclR5cGUiOiJTRUxGIiwid2ViaG9va1VybCI6Imh0dHA6Ly8xMjcuMC4wLjE6ODAwMC9kaGFuL2NhbGxiYWNrIiwiZGhhbkNsaWVudElkIjoiMTEwOTEyMTg5OCJ9.HCZKDfs3x15YIZVEU6Ql4cMArJsP5eRpTTKhWmEBPY1yDlifF3jte1IMbKVY5QjLRXxeFZKXaToCQwn1EkRe3Q"



# # Initialize the API client with your Client ID and Access Token
# # client_id = "YOUR_CLIENT_ID"
# # access_token = "YOUR_ACCESS_TOKEN"
# api = DhanHQAPI(client_id=client_id, access_token=access_token)

# # Example: Fetching market quote for an instrument
# # You need the correct security ID and exchange segment from the Dhan instrument list
# security_id = "YOUR_SECURITY_ID" # e.g., "13" for a specific stock on NSE
# exchange_segment = "NSE_EQ" # or "BSE_EQ", "NSE_FNO", etc.

# try:
#     quote = api.get_market_quote(
#         security_id=security_id,
#         exchange_segment=exchange_segment
#     )
#     print("Market Quote:", quote)

#     # Example: Fetching historical data
#     # Specify the date range in YYYY-MM-DD format
#     from_date = "2024-01-01"
#     to_date = "2024-01-10"
#     interval = "1" # Minute intervals: 1, 5, 15, 25, 60

#     historical_data = api.get_intraday_charts(
#         securityId=security_id,
#         exchangeSegment=exchange_segment,
#         instrument="EQUITY", # or "DERIVATIVE"
#         interval=interval,
#         fromDate=from_date,
#         toDate=to_date
#     )
#     # The data often comes in JSON and can be converted to a Pandas DataFrame for analysis
#     if historical_data and 'data' in historical_data:
#         df = pd.DataFrame(historical_data['data'])
#         print("Historical Data (DataFrame Head):")
#         print(df.head())
#     else:
#         print("No historical data received.")

# except Exception as e:
#     print(f"An error occurred: {e}")


# test_instruments.py
# from app.services import dhan_service

# data = dhan_service.load_instruments(force_reload=True)
# print(f"Loaded {len(data)} instruments")

# # show first few for inspection
# for inst in data[:5]:
#     print(inst)

# from app.services import dhan_service

# print(dhan_service.find_instrument("RELIANCE"))
# print(dhan_service.find_instrument("TRIDENT"))
# print(dhan_service.find_instrument("HDFCBANK"))

# import pandas as pd

# df = pd.read_csv("app/data/instruments.csv", low_memory=False)

# # Look for any rows mentioning 'RELIANCE'
# sample = df[
#     df.apply(lambda row: row.astype(str).str.contains("RELIANCE", case=False).any(), axis=1)
# ]

# print(sample.head(10).to_dict(orient="records"))
# print(f"Columns: {list(df.columns)}")


# CLIENT_ID = "1109121898"
# ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJwX2lwIjoiIiwic19pcCI6IiIsImlzcyI6ImRoYW4iLCJwYXJ0bmVySWQiOiIiLCJleHAiOjE3NjI3NzgxMzUsImlhdCI6MTc2MjY5MTczNSwidG9rZW5Db25zdW1lclR5cGUiOiJTRUxGIiwid2ViaG9va1VybCI6Imh0dHA6Ly8xMjcuMC4wLjE6ODAwMC9kaGFuL2NhbGxiYWNrIiwiZGhhbkNsaWVudElkIjoiMTEwOTEyMTg5OCJ9.HCZKDfs3x15YIZVEU6Ql4cMArJsP5eRpTTKhWmEBPY1yDlifF3jte1IMbKVY5QjLRXxeFZKXaToCQwn1EkRe3Q"

# DATA_DIR = "app/data"
# os.makedirs(DATA_DIR, exist_ok=True)
# LOCAL_PATH = os.path.join(DATA_DIR, "instruments_nse_eq.csv")

# url = "https://dataapi.dhan.co/instruments/NSE_EQ"
# headers = {
#     "client-id": CLIENT_ID,
#     "access-token": ACCESS_TOKEN
# }

# print(f"⬇️ Fetching NSE_EQ instruments from {url}")
# resp = requests.get(url, headers=headers)

# if resp.status_code == 200:
#     with open(LOCAL_PATH, "wb") as f:
#         f.write(resp.content)
#     print(f"✅ Saved NSE_EQ instrument master → {LOCAL_PATH}")
# else:
#     print(f"❌ Failed: {resp.status_code} -> {resp.text}")

# url = "https://13.232.115.240/instruments/NSE_EQ"
# headers = {
#     "Host": "dataapi.dhan.co",
#     "client-id": "1109121898",
#     "access-token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJwX2lwIjoiIiwic19pcCI6IiIsImlzcyI6ImRoYW4iLCJwYXJ0bmVySWQiOiIiLCJleHAiOjE3NjI3NzgxMzUsImlhdCI6MTc2MjY5MTczNSwidG9rZW5Db25zdW1lclR5cGUiOiJTRUxGIiwid2ViaG9va1VybCI6Imh0dHA6Ly8xMjcuMC4wLjE6ODAwMC9kaGFuL2NhbGxiYWNrIiwiZGhhbkNsaWVudElkIjoiMTEwOTEyMTg5OCJ9.HCZKDfs3x15YIZVEU6Ql4cMArJsP5eRpTTKhWmEBPY1yDlifF3jte1IMbKVY5QjLRXxeFZKXaToCQwn1EkRe3Q"
# }

# r = requests.get(url, headers=headers, verify=False)
# print(r.status_code, len(r.content))



# url = "https://dataapi.dhan.co/instruments/NSE_EQ"
# headers = {
#     "client-id": "1109121898",
#     "access-token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJwX2lwIjoiIiwic19pcCI6IiIsImlzcyI6ImRoYW4iLCJwYXJ0bmVySWQiOiIiLCJleHAiOjE3NjI3NzgxMzUsImlhdCI6MTc2MjY5MTczNSwidG9rZW5Db25zdW1lclR5cGUiOiJTRUxGIiwid2ViaG9va1VybCI6Imh0dHA6Ly8xMjcuMC4wLjE6ODAwMC9kaGFuL2NhbGxiYWNrIiwiZGhhbkNsaWVudElkIjoiMTEwOTEyMTg5OCJ9.HCZKDfs3x15YIZVEU6Ql4cMArJsP5eRpTTKhWmEBPY1yDlifF3jte1IMbKVY5QjLRXxeFZKXaToCQwn1EkRe3Q"
# }

# resp = requests.get(url, headers=headers, verify=False)
# print(resp.status_code)
# print(resp.text[:500])


# url = "https://13.232.115.240/instruments/NSE_EQ"  # Use IP directly
# headers = {
#     "Host": "dataapi.dhan.co",          # Required for TLS handshake & routing
#     "client-id": "1109121898",
#     "access-token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJwX2lwIjoiIiwic19pcCI6IiIsImlzcyI6ImRoYW4iLCJwYXJ0bmVySWQiOiIiLCJleHAiOjE3NjI3NzgxMzUsImlhdCI6MTc2MjY5MTczNSwidG9rZW5Db25zdW1lclR5cGUiOiJTRUxGIiwid2ViaG9va1VybCI6Imh0dHA6Ly8xMjcuMC4wLjE6ODAwMC9kaGFuL2NhbGxiYWNrIiwiZGhhbkNsaWVudElkIjoiMTEwOTEyMTg5OCJ9.HCZKDfs3x15YIZVEU6Ql4cMArJsP5eRpTTKhWmEBPY1yDlifF3jte1IMbKVY5QjLRXxeFZKXaToCQwn1EkRe3Q"
# }

# resp = requests.get(url, headers=headers, verify=False)  # Verify False avoids mismatch
# print(resp.status_code)
# print(resp.text[:500])


# import requests, json

# url = "https://api.dhan.co/v2/marketfeed/ltp"
# headers = {
#     "client-id": "1109121898",
#     "access-token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJwX2lwIjoiIiwic19pcCI6IiIsImlzcyI6ImRoYW4iLCJwYXJ0bmVySWQiOiIiLCJleHAiOjE3NjI3NzgxMzUsImlhdCI6MTc2MjY5MTczNSwidG9rZW5Db25zdW1lclR5cGUiOiJTRUxGIiwid2ViaG9va1VybCI6Imh0dHA6Ly8xMjcuMC4wLjE6ODAwMC9kaGFuL2NhbGxiYWNrIiwiZGhhbkNsaWVudElkIjoiMTEwOTEyMTg5OCJ9.HCZKDfs3x15YIZVEU6Ql4cMArJsP5eRpTTKhWmEBPY1yDlifF3jte1IMbKVY5QjLRXxeFZKXaToCQwn1EkRe3Q",
#     "Content-Type": "application/json"
# }
# body = {
#     "symbols": ["NSE_EQ:RELIANCE", "NSE_EQ:TCS"]
# }

# resp = requests.post(url, headers=headers, json=body)
# print(resp.status_code)
# print(json.dumps(resp.json(), indent=2))

# import requests, json

# url = "https://api.dhan.co/v2/instruments"
# headers = {
#     "client-id": "1109121898",
#     "access-token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJwX2lwIjoiIiwic19pcCI6IiIsImlzcyI6ImRoYW4iLCJwYXJ0bmVySWQiOiIiLCJleHAiOjE3NjI3NzgxMzUsImlhdCI6MTc2MjY5MTczNSwidG9rZW5Db25zdW1lclR5cGUiOiJTRUxGIiwid2ViaG9va1VybCI6Imh0dHA6Ly8xMjcuMC4wLjE6ODAwMC9kaGFuL2NhbGxiYWNrIiwiZGhhbkNsaWVudElkIjoiMTEwOTEyMTg5OCJ9.HCZKDfs3x15YIZVEU6Ql4cMArJsP5eRpTTKhWmEBPY1yDlifF3jte1IMbKVY5QjLRXxeFZKXaToCQwn1EkRe3Q"
# }
# resp = requests.get(url, headers=headers)
# print(resp.status_code)
# print(resp.text[:500])

# import requests, json

# url = "https://api.dhan.co/v2/marketfeed/ltp"
# headers = {
#     "client-id": "2511099893",
#     "access-token": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJwX2lwIjoiIiwic19pcCI6IiIsImlzcyI6ImRoYW4iLCJwYXJ0bmVySWQiOiIiLCJleHAiOjE3NjU0MjI0MDAsImlhdCI6MTc2NTMzNjgwMCwidG9rZW5Db25zdW1lclR5cGUiOiJTRUxGIiwid2ViaG9va1VybCI6Imh0dHA6Ly8xMjcuMC4wLjE6ODAwMC9kaGFuL2NhbGxiYWNrIiwiZGhhbkNsaWVudElkIjoiMjUxMTA5OTg5MyJ9.Ze0Z1Y8mXo3Z8u1kTt1Z5bYFqIY1nYk1vU4rXjXoZV1w7Y2Fq3ZkQeXl3QKXJc3K5j3Z0QH3j3QKXl3Q",
#     "Content-Type": "application/json"
# }
# body = {"symbols": ["NSE_EQ:RELIANCE", "NSE_EQ:TCS"]}
# r = requests.post(url, headers=headers, json=body)
# print(json.dumps(r.json(), indent=2))

# import redis
# r = redis.Redis(host="localhost", port=6379)
# print(r.info())

# from redis import Redis
# r = Redis(host="127.0.0.1", port=6379, db=0, decode_responses=True)
# print("PING:", r.ping())
# print("INFO server:", {k: v for k, v in r.info(section='server').items() if k in ('redis_version','server')})
# print("KEYS count sample:", len(r.keys("*")))
# print("SAMPLE KEYS (first 50):", r.keys("*")[:50])

import redis
r = redis.Redis(host="127.0.0.1", port=6379, db=0, decode_responses=True)
print(r.connection_pool.connection_kwargs)



# """
# Quick test script you can run from backend/app:
# python -m app.test

# It hits your local endpoints and prints responses.
# """
# import requests, json
# BASE = "http://127.0.0.1:8000"

# def p(r):
#     try:
#         print(json.dumps(r.json(), indent=2))
#     except Exception:
#         print(r.text)

# print("GET /stocks")
# p(requests.get(BASE + "/stocks"))

# print("GET /portfolio")
# p(requests.get(BASE + "/portfolio"))

# print("GET /history")
# p(requests.get(BASE + "/history"))

# print("TRY trade (simulated buy 1 RELIANCE)")
# r = requests.post(BASE + "/trade", json={"symbol":"RELIANCE","amount":1,"type":"buy"})
# p(r)


