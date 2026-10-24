"""Trigger an outbound call with Twilio.

Setup:
    pip install twilio

Set credentials as environment variables (never hard-code them):
    export TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    export TWILIO_AUTH_TOKEN="your_auth_token"
    export TWILIO_FROM_NUMBER="+1XXXXXXXXXX"   # your active Twilio number
    export TO_NUMBER="+91XXXXXXXXXX"           # your phone number (E.164 format)

Run:
    python make_call.py
"""

import os
import sys

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

# Twilio's demo TwiML endpoint: plays a short welcome message when answered
TWIML_URL = "https://demo.twilio.com/welcome/voice/"


def main() -> None:
    try:
        account_sid = "ACdb0a15ae590abc5a7e8e929c428bbd5f"
        auth_token = "303c5c030c3b97051ae54c93a938749f"
        from_number = "+17402763138"
        to_number = "+919444713670"
    except KeyError as e:
        sys.exit(f"Missing environment variable: {e}")

    client = Client(account_sid, auth_token)

    try:
        call = client.calls.create(
            to=to_number,
            from_=from_number,
            url=TWIML_URL,
        )
    except TwilioRestException as e:
        sys.exit(f"Twilio error {e.code}: {e.msg}")

    print(f"Call started. SID: {call.sid}, status: {call.status}")


if __name__ == "__main__":
    main()