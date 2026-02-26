import asyncio
import re
import os
import json
from datetime import datetime
from aiohttp import web
from telethon import TelegramClient
from telethon.sessions import StringSession

routes = web.RouteTableDef()

client = None
BOT = "OSINT_INFO_FATHER_BOT"
HISTORY_FILE = "history.json"


# ---------------- JSON ---------------- #

def j(data):
    return web.json_response(data)


# ---------------- HISTORY ---------------- #

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []


def save_history():
    with open(HISTORY_FILE, "w") as f:
        json.dump(HISTORY, f, indent=2)


HISTORY = load_history()


# ---------------- HOME ---------------- #

@routes.get("/")
async def home(request):
    return j({
        "status": True,
        "total": len(HISTORY),
        "history": HISTORY[::-1]
    })


# ---------------- PARSER ---------------- #

def parse_leak(text):

    phones = re.findall(r'\b\d{10,13}\b', text)

    names = re.findall(r'Full.?Name\s*:?\s*(.+)', text, re.I)
    fathers = re.findall(r'Father.?Name\s*:?\s*(.+)', text, re.I)
    addresses = re.findall(r'Address\s*:?\s*(.+)', text, re.I)
    regions = re.findall(r'Region\s*:?\s*(.+)', text, re.I)
    docs = re.findall(r'Document\s*number\s*:?\s*(\d+)', text, re.I)

    return {
        "telephones": list(set(phones)),
        "addresses": list(set(addresses)),
        "document_numbers": docs,
        "full_names": names,
        "father_names": fathers,
        "regions": regions
    }


# ---------------- CONNECT ---------------- #

async def ensure_connected():
    global client

    if client is None:
        raise Exception("login required")

    if not client.is_connected():
        await client.connect()


# ---------------- FETCH ---------------- #

async def fetch_all_pages(number):

    await ensure_connected()

    all_text = ""

    await client.send_message(BOT, number)

    await asyncio.sleep(10)

    msgs = await client.get_messages(BOT, limit=5)
    message = next((m for m in msgs if m.message), None)

    if not message:
        return ""

    all_text += message.message + "\n"

    while message.buttons:

        next_btn = None

        for row in message.buttons:
            for btn in row:
                if "➡" in btn.text or ">" in btn.text:
                    next_btn = btn.text
                    break

        if not next_btn:
            break

        await message.click(text=next_btn)
        await asyncio.sleep(6)

        msgs = await client.get_messages(BOT, limit=5)

        for m in msgs:
            if m.id != message.id and m.message:
                message = m
                all_text += message.message + "\n"
                break

    return all_text


# ---------------- LOGIN ---------------- #

@routes.get("/login/start/{api_id}/{api_hash}/{session}")
async def login_start(request):
    global client

    try:
        api_id = int(request.match_info["api_id"])
        api_hash = request.match_info["api_hash"]
        session_string = request.match_info["session"]

        client = TelegramClient(
            StringSession(session_string),
            api_id,
            api_hash
        )

        await client.start()

        asyncio.create_task(client.run_until_disconnected())

        me = await client.get_me()

        return j({
            "status": True,
            "user": me.first_name
        })

    except Exception as e:
        return j({"status": False, "error": str(e)})


# ---------------- NUMBER API ---------------- #

@routes.get("/number")
async def number_info(request):
    try:

        number = request.query.get("info")

        if not number:
            return j({"status": False, "error": "number missing"})

        number = "91" + number

        text = await fetch_all_pages(number)

        if not text:
            return j({"status": True, "data": []})

        parsed = parse_leak(text)

        # SAVE HISTORY
        if not any(x["number"] == number for x in HISTORY):

            HISTORY.append({
                "number": number,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data": parsed
            })

            save_history()

        return j({
            "status": True,
            "data": parsed
        })

    except Exception as e:
        return j({"status": False, "error": str(e)})


# ---------------- START ---------------- #

app = web.Application()
app.add_routes(routes)

web.run_app(app, port=int(os.environ.get("PORT", 8080)))
