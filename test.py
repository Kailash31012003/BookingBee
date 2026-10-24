
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

load_dotenv()

app = FastAPI(title="BookingBee SMS API")

ACCOUNT_SID = os.getenv("ACCOUNT_SID")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
FROM_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

if not all([ACCOUNT_SID, AUTH_TOKEN, FROM_NUMBER]):
    raise RuntimeError("Missing Twilio credentials in .env")

client = Client(ACCOUNT_SID, AUTH_TOKEN)


# Request body model
class SMSRequest(BaseModel):
    MessageBody: str = Field(min_length=1)
    phNo: list[str] = Field(min_length=1)


# Endpoint 1: Send SMS to one number
@app.post("/send-sms")
def send_sms(request: SMSRequest):
    phone = request.phNo[0]

    try:
        message = client.messages.create(
            body=request.MessageBody,
            from_=FROM_NUMBER,
            to=phone
        )

        return {
            "success": True,
            "phone": phone,
            "message_sid": message.sid,
            "status": message.status
        }

    except TwilioRestException as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )


# Endpoint 2: Send SMS to multiple numbers
@app.post("/send-bulk-sms")
def send_bulk_sms(request: SMSRequest):
    results = []

    for phone in request.phNo:
        try:
            message = client.messages.create(
                body=request.MessageBody,
                from_=FROM_NUMBER,
                to=phone
            )

            results.append({
                "phone": phone,
                "success": True,
                "message_sid": message.sid,
                "status": message.status
            })

        except TwilioRestException as exc:
            results.append({
                "phone": phone,
                "success": False,
                "error": str(exc)
            })

    return {
        "message": "SMS processing completed",
        "total": len(request.phNo),
        "results": results
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)