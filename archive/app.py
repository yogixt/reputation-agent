"""
Reputation Agent - Production API
FastAPI backend with REST + WebSocket
"""

import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import database as db
from agent import agent

app = FastAPI(title="Reputation Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

clients = []

async def broadcast(data):
    dead = []
    for client in clients:
        try:
            await client.send_json(data)
        except:
            dead.append(client)
    for client in dead:
        if client in clients:
            clients.remove(client)

@app.on_event("startup")
async def startup():
    db.init_db()
    agent.start()
    asyncio.create_task(poll_loop())

@app.on_event("shutdown")
async def shutdown():
    agent.stop()

async def poll_loop():
    while True:
        await asyncio.sleep(3)
        try:
            stats = db.get_stats()
            logs = db.get_agent_logs(30)
            domains = db.get_domains()
            accounts = db.get_accounts()
            await broadcast({
                "type": "update",
                "stats": stats,
                "logs": logs,
                "domains": domains,
                "accounts": accounts,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            print(f"Poll error: {e}")

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    with open("static/index.html") as f:
        return f.read()

# ============ REST API ============

@app.get("/api/stats")
def api_stats():
    return db.get_stats()

@app.get("/api/domains")
def api_domains():
    rows = db.get_domains()
    return [{"id": r[0], "domain": r[1], "sender_email": r[2], "status": r[3], "daily_target": r[4], "current_week": r[5]} for r in rows]

@app.post("/api/domains")
async def api_add_domain(request: Request):
    data = await request.json()
    domain_id = db.add_domain(data["domain"], data["sender_email"], data.get("daily_target", 5))
    await broadcast({"type": "domain_added", "id": domain_id})
    return {"success": True, "id": domain_id}

@app.delete("/api/domains/{domain_id}")
def api_delete_domain(domain_id: int):
    db.delete_domain(domain_id)
    asyncio.create_task(broadcast({"type": "domain_deleted"}))
    return {"success": True}

@app.get("/api/accounts")
def api_accounts():
    rows = db.get_accounts()
    return [{"id": r[0], "email": r[1], "role": r[3], "status": r[4]} for r in rows]

@app.post("/api/accounts")
async def api_add_account(request: Request):
    data = await request.json()
    account_id = db.add_account(data["email"], data["password"], data.get("role", "peer"))
    await broadcast({"type": "account_added", "id": account_id})
    return {"success": True, "id": account_id}

@app.delete("/api/accounts/{account_id}")
def api_delete_account(account_id: int):
    db.delete_account(account_id)
    asyncio.create_task(broadcast({"type": "account_deleted"}))
    return {"success": True}

@app.get("/api/reputation")
def api_reputation(domain_id: int = 1):
    history = db.get_reputation_history(domain_id, 30)
    return [{"date": r[0], "sent": r[1], "moved": r[2], "opened": r[3], "replied": r[4], "score": r[5], "inbox_rate": r[6]} for r in history]

@app.get("/api/sends")
def api_sends(limit: int = 50):
    rows = db.get_recent_sends(limit)
    return [{"id": r[0], "from": r[2], "to": r[3], "subject": r[4], "status": r[6], "time": r[7]} for r in rows]

@app.get("/api/logs")
def api_logs(limit: int = 100):
    rows = db.get_agent_logs(limit)
    return [{"id": r[0], "level": r[1], "message": r[2], "time": r[3]} for r in rows]

@app.post("/api/agent/start")
def api_start_agent():
    if not agent.running:
        agent.start()
    return {"running": agent.running}

@app.post("/api/agent/stop")
def api_stop_agent():
    agent.stop()
    return {"running": agent.running}

@app.get("/api/agent/status")
def api_agent_status():
    return {"running": agent.running}

# ============ WEBSOCKET ============

@app.websocket("/ws")
async def websocket(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            await handle_ws_message(data, websocket)
    except WebSocketDisconnect:
        if websocket in clients:
            clients.remove(websocket)

async def handle_ws_message(data, ws):
    action = data.get("action")
    if action == "get_reputation":
        history = db.get_reputation_history(data.get("domain_id", 1), 30)
        await ws.send_json({"type": "reputation_history", "data": history})
    elif action == "get_sends":
        sends = db.get_recent_sends(50)
        await ws.send_json({"type": "sends", "data": sends})
    elif action == "start_agent":
        if not agent.running:
            agent.start()
        await ws.send_json({"type": "agent_status", "running": agent.running})
    elif action == "stop_agent":
        agent.stop()
        await ws.send_json({"type": "agent_status", "running": agent.running})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
