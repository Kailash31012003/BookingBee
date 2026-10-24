"""
BookingBee voice AI: Twilio outbound call <-> OpenAI Realtime (gpt-realtime-1.5).

Install:
    pip install fastapi uvicorn twilio python-dotenv "websockets>=14"

.env:
    API_KEY=<secret for the x-api-key header on /make-call>
    OPENAI_API_KEY=sk-...
    OPENAI_REALTIME_MODEL=gpt-realtime-1.5
    OPENAI_VOICE=marin
    TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TWILIO_FROM_NUMBER=+17402763138
    PUBLIC_BASE_URL=https://34f9-14-96-237-250.ngrok-free.app

Run:
    uvicorn ai_voice_server:app --host 0.0.0.0 --port 5050
    ngrok http 5050

Trigger a call (or use call_trigger.py with url=PUBLIC_BASE_URL + "/voice"):
    POST /make-call  {"to": "+919444713670", "customer_name": "Arun", "purpose": "a BookingBee follow-up"}
"""

import asyncio
import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
import uvicorn
import websockets
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.responses import Response
from pydantic import BaseModel, Field
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, VoiceResponse

load_dotenv()

API_KEY = os.getenv("API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-1.5")
VOICE = os.getenv("OPENAI_VOICE", "marin")
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

OPENAI_WS_URL = f"wss://api.openai.com/v1/realtime?model={MODEL}"
E164 = re.compile(r"^\+[1-9]\d{7,14}$")

SYSTEM_PROMPT = """You are a friendly voice assistant calling on behalf of BookingBee, on a live outbound phone call.
You are calling {name} to ask if they would like to book a salon appointment.
Be warm, brief and natural: one or two short sentences at a time, no lists or markdown.

CALL FLOW:
1. After the greeting, ask if they would like to book a salon appointment. Never ask "How can I assist you" or similar.
2. If they are interested, collect the service, the date and the time. Ask for one missing detail at a time.
   Read the details back and get a clear yes, then call the book_appointment tool.
   After the tool succeeds, say the appointment is noted and the salon will confirm it, then thank them and say goodbye.
3. If they are NOT interested, are unsure, or hesitate, then and only then mention the offers:
   - 10% off on haircuts
   - 20% off on all other services
   Mention them once, naturally, and ask if that changes their mind. Do not mention offers before this point.
4. If they still say no, or say it is a bad time, thank them politely and say goodbye. Do not push again.

RULES:
- Never invent offers, prices, availability or policies beyond what is stated here. If asked something you do not know, say the salon team will follow up.
- Do not claim a booking is saved unless the tool returned success.
- Speak English by default, and switch language if the person speaks another one."""

BOOKINGS_FILE = Path(os.getenv("BOOKINGS_FILE", Path(__file__).resolve().parent / "bookings.txt"))

TOOLS = [
    {
        "type": "function",
        "name": "book_appointment",
        "description": "Save a salon appointment request after the customer has confirmed "
                       "the service, date and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Customer's name"},
                "service": {"type": "string",
                            "description": "Requested service, e.g. haircut, facial, manicure"},
                "date": {"type": "string",
                         "description": "Appointment date, e.g. 2026-10-27 or 'next Monday'"},
                "time": {"type": "string", "description": "Appointment time, e.g. 4:30 PM"},
                "notes": {"type": "string", "description": "Any extra requests (optional)"},
            },
            "required": ["customer_name", "service", "date", "time"],
        },
    }
]


def save_booking(args: dict, phone: str) -> dict:
    """Append one booking as a line of text to bookings.txt."""
    try:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = (
            f"[{stamp}] name={args.get('customer_name', '')} | phone={phone} | "
            f"service={args.get('service', '')} | date={args.get('date', '')} | "
            f"time={args.get('time', '')} | notes={args.get('notes', '') or '-'}\n"
        )
        with BOOKINGS_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
        print("Booking saved:", line.strip())
        return {"success": True, "message": "Appointment request saved."}
    except Exception as e:
        print("Failed to save booking:", repr(e))
        return {"success": False, "message": "Could not save the appointment."}


app = FastAPI(title="BookingBee Voice AI")


def require_api_key(x_api_key: str = Header(default="")):
    if not API_KEY or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(401, detail={"message": "Invalid or missing API key"})


class CallRequest(BaseModel):
    to: str
    customer_name: str = Field(default="there", max_length=80)
    purpose: str = Field(default="a BookingBee follow-up", max_length=200)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}


@app.post("/make-call", dependencies=[Depends(require_api_key)])
def make_call(req: CallRequest):
    if not E164.match(req.to):
        raise HTTPException(422, detail={"message": "'to' must be E.164, e.g. +919444713670"})
    if not (ACCOUNT_SID and AUTH_TOKEN and FROM_NUMBER and PUBLIC_BASE_URL):
        raise HTTPException(500, detail={"message": "Twilio / PUBLIC_BASE_URL env vars missing"})

    url = f"{PUBLIC_BASE_URL}/voice?" + urlencode(
        {"name": req.customer_name, "purpose": req.purpose}
    )
    try:
        call = Client(ACCOUNT_SID, AUTH_TOKEN).calls.create(
            to=req.to, from_=FROM_NUMBER, url=url, method="POST"
        )
    except TwilioRestException as e:
        raise HTTPException(
            502,
            detail={"message": "Twilio could not create the call",
                    "twilio_code": e.code, "twilio_message": e.msg},
        )
    return {"status": "queued", "call_sid": call.sid}


@app.api_route("/voice", methods=["GET", "POST"])
async def voice(request: Request):
    """Twilio fetches this when the call is answered; it opens the media stream."""
    name = request.query_params.get("name", "there")
    purpose = request.query_params.get("purpose", "a BookingBee follow-up")
    ws_url = PUBLIC_BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/media-stream"

    # Twilio posts the called number as "To" on outbound calls.
    phone = ""
    if request.method == "POST":
        try:
            phone = (await request.form()).get("To", "")
        except Exception:
            phone = ""

    vr = VoiceResponse()
    connect = Connect()
    stream = connect.stream(url=ws_url)
    stream.parameter(name="name", value=name)
    stream.parameter(name="purpose", value=purpose)
    stream.parameter(name="phone", value=phone)
    vr.append(connect)
    return Response(content=str(vr), media_type="application/xml")


@app.websocket("/media-stream")
async def media_stream(twilio_ws: WebSocket):
    await twilio_ws.accept()

    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY missing")
        await twilio_ws.close()
        return

    async with websockets.connect(
        OPENAI_WS_URL,
        additional_headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
    ) as openai_ws:
        state = {"stream_sid": None, "response_active": False, "phone": ""}

        async def configure_session(name: str, purpose: str):
            await openai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "model": MODEL,
                    "output_modalities": ["audio"],
                    "instructions": SYSTEM_PROMPT.format(name=name, purpose=purpose),
                    "tools": TOOLS,
                    "tool_choice": "auto",
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcmu"},  # Twilio's 8kHz mu-law
                            "turn_detection": {"type": "server_vad"},
                        },
                        "output": {
                            "format": {"type": "audio/pcmu"},
                            "voice": VOICE,
                        },
                    },
                },
            }))
            # The AI speaks first on an outbound call.
            await openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "instructions": f"Greet {name} warmly, say you are calling from BookingBee, "
                                    "and ask if they would like to book a salon appointment. "
                                    "Do not mention any offers yet."
                },
            }))

        async def twilio_to_openai():
            try:
                while True:
                    msg = json.loads(await twilio_ws.receive_text())
                    event = msg.get("event")
                    if event == "start":
                        state["stream_sid"] = msg["start"]["streamSid"]
                        params = msg["start"].get("customParameters", {})
                        state["phone"] = params.get("phone", "")
                        print("Call started:", state["stream_sid"], params)
                        await configure_session(
                            params.get("name", "there"),
                            params.get("purpose", "a BookingBee follow-up"),
                        )
                    elif event == "media":
                        await openai_ws.send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": msg["media"]["payload"],
                        }))
                    elif event == "stop":
                        print("Call ended")
                        break
            except Exception as e:  # WebSocketDisconnect etc.
                print("twilio_to_openai ended:", repr(e))
            finally:
                await openai_ws.close()

        async def openai_to_twilio():
            try:
                async for raw in openai_ws:
                    ev = json.loads(raw)
                    t = ev.get("type")

                    if t in ("response.output_audio.delta", "response.audio.delta"):
                        if state["stream_sid"]:
                            await twilio_ws.send_text(json.dumps({
                                "event": "media",
                                "streamSid": state["stream_sid"],
                                "media": {"payload": ev["delta"]},
                            }))
                    elif t == "response.function_call_arguments.done":
                        # The model asked to run a tool: run it, return the result, let it continue.
                        result = {"success": False, "message": f"Unknown tool {ev.get('name')}"}
                        if ev.get("name") == "book_appointment":
                            try:
                                args = json.loads(ev.get("arguments") or "{}")
                                result = await asyncio.to_thread(save_booking, args, state["phone"])
                            except Exception as e:
                                print("book_appointment failed:", repr(e))
                                result = {"success": False, "message": "Invalid booking details."}
                        await openai_ws.send(json.dumps({
                            "type": "conversation.item.create",
                            "item": {
                                "type": "function_call_output",
                                "call_id": ev["call_id"],
                                "output": json.dumps(result),
                            },
                        }))
                        await openai_ws.send(json.dumps({"type": "response.create"}))
                    elif t == "response.created":
                        state["response_active"] = True
                    elif t == "response.done":
                        state["response_active"] = False
                    elif t == "input_audio_buffer.speech_started":
                        # Caller interrupted: flush audio already queued at Twilio.
                        if state["stream_sid"]:
                            await twilio_ws.send_text(json.dumps({
                                "event": "clear",
                                "streamSid": state["stream_sid"],
                            }))
                        if state["response_active"]:
                            await openai_ws.send(json.dumps({"type": "response.cancel"}))
                    elif t == "error":
                        print("OpenAI error:", ev.get("error"))
            except Exception as e:
                print("openai_to_twilio ended:", repr(e))

        await asyncio.gather(twilio_to_openai(), openai_to_twilio())

# Run directly using python main.py
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=5050,
    )
