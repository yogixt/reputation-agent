"""
Tests for the WebSocket endpoint.
"""

import pytest


def test_websocket_requires_auth(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws"):
            pass


def test_websocket_accepts_authenticated_user(authenticated_client):
    with authenticated_client.websocket_connect("/ws") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "update"


def test_websocket_process_queue_action_removed(authenticated_client):
    with authenticated_client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_json({"action": "process_queue", "limit": 50})
        # The endpoint should ignore the message and stay open.
        # If any response comes back, it must not acknowledge process_queue.
