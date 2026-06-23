"""
WebSocket endpoint for real-time dashboard updates.

NOTE: WebSocket broadcasts use an in-memory client list. On multi-instance
serverless deployments (e.g. Vercel) broadcasts will only reach clients
connected to the same instance. This endpoint is authenticated.
"""

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

import auth as auth_module
from services import account_service, campaign_service, log_service, stats_service
from services.email_queue_service import get_queue
from services.reputation_service import get_latest_scores

router = APIRouter(tags=["websocket"])
clients = []


async def _close_unauthenticated(websocket: WebSocket):
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


async def broadcast(data: dict):
    dead = []
    for client in clients:
        try:
            await client.send_json(data)
        except Exception:
            dead.append(client)
    for client in dead:
        if client in clients:
            clients.remove(client)


async def poll_broadcast_loop():
    while True:
        await asyncio.sleep(3)
        try:
            await broadcast({
                "type": "update",
                "stats": stats_service.get_stats(),
                "logs": log_service.get_logs(30),
                "campaigns": campaign_service.list_campaigns(),
                "accounts": account_service.list_accounts(),
                "queue": get_queue(limit=20),
                "latest_scores": get_latest_scores(),
                "timestamp": __import__("db").now(),
            })
        except Exception as e:
            print(f"Broadcast error: {e}")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        auth_module.get_session_from_scope(websocket.scope)
    except Exception:
        await _close_unauthenticated(websocket)
        return

    await websocket.accept()
    clients.append(websocket)
    try:
        await websocket.send_json({
            "type": "update",
            "stats": stats_service.get_stats(),
            "logs": log_service.get_logs(30),
            "campaigns": campaign_service.list_campaigns(),
            "accounts": account_service.list_accounts(),
            "queue": get_queue(limit=20),
            "latest_scores": get_latest_scores(),
        })
        while True:
            # Keep connection alive; ignore incoming messages.
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in clients:
            clients.remove(websocket)
    except Exception:
        if websocket in clients:
            clients.remove(websocket)
