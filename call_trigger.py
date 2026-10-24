import os
from pathlib import Path
from dotenv import load_dotenv
from twilio.rest import Client

env_path = Path(__file__).resolve().parent / ".env"
print(".env found:", env_path.exists(), "->", env_path)
load_dotenv(env_path, override=True)

ACCOUNT_SID = os.getenv("ACCOUNT_SID")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "+17402763138")

missing = [k for k, v in {
    "TWILIO_ACCOUNT_SID": ACCOUNT_SID,
    "TWILIO_AUTH_TOKEN": AUTH_TOKEN,
}.items() if not v]
if missing:
    raise SystemExit(f"Missing in .env: {', '.join(missing)}")

client = Client(ACCOUNT_SID, AUTH_TOKEN)

call = client.calls.create(
    to="+13023033120",
    from_=FROM_NUMBER,
    url="https://e7e7-14-96-237-250.ngrok-free.app/voice?name=Arun&purpose=a%20BookingBee%20follow-up",
)
print("Call SID:", call.sid)