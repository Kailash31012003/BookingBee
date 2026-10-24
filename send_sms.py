
import os
import csv
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

load_dotenv()

ACCOUNT_SID = os.getenv("ACCOUNT_SID")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
FROM_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

if not all([ACCOUNT_SID, AUTH_TOKEN, FROM_NUMBER]):
    raise ValueError("Missing Twilio credentials in .env")

client = Client(ACCOUNT_SID, AUTH_TOKEN)

MESSAGE_BODY = (
    "Hello! This is an announcement from BookingBee. "
    "10 % offer"
)

INPUT_FILE = "recipients.csv"
LOG_FILE = "sent_log.csv"

def send_bulk_sms():
    with open(INPUT_FILE, newline="", encoding="utf-8-sig") as file:
        recipients = [
            row["phone"].strip()
            for row in csv.DictReader(file)
            if row.get("phone", "").strip()
        ]

    # Create the log file with a header if it doesn't exist.
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as log:
            writer = csv.writer(log)
            writer.writerow([
                "timestamp", "phone", "status", "message_sid", "error"
            ])

    print(f"Recipients loaded: {len(recipients)}")

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as log:
        writer = csv.writer(log)

        for index, phone in enumerate(recipients, start=1):
            try:
                message = client.messages.create(
                    body=MESSAGE_BODY,
                    from_=FROM_NUMBER,
                    to=phone,
                )

                print(f"[{index}/{len(recipients)}] "
                      f"{phone}: {message.status} ({message.sid})")

                writer.writerow([
                    datetime.now(timezone.utc).isoformat(),
                    phone,
                    message.status,
                    message.sid,
                    "",
                ])

            except TwilioRestException as exc:
                print(f"[{index}/{len(recipients)}] "
                      f"{phone}: FAILED - {exc}")

                writer.writerow([
                    datetime.now(timezone.utc).isoformat(),
                    phone,
                    "failed",
                    "",
                    str(exc),
                ])

            except Exception as exc:
                print(f"{phone}: ERROR - {exc}")
                writer.writerow([
                    datetime.now(timezone.utc).isoformat(),
                    phone,
                    "error",
                    "",
                    str(exc),
                ])

            log.flush()

            time.sleep(1)

    print("Bulk SMS submission finished. Check sent_log.csv.")

def send_test_sms():
    TO_NUMBER = "+919444713670"  

    try:
        message = client.messages.create(
            body=MESSAGE_BODY,
            from_=FROM_NUMBER,
            to=TO_NUMBER,
        )

        print(f"SMS submitted successfully!")
        print(f"To: {TO_NUMBER}")
        print(f"Message SID: {message.sid}")
        print(f"Status: {message.status}")

    except TwilioRestException as exc:
        print(f"Twilio error: {exc}")

if __name__ == "__main__":
    send_test_sms()
