from fastapi import APIRouter

router = APIRouter(prefix="/api/websocket", tags=["WebSocket"])


@router.get(
    "/protocol",
    summary="WebSocket Protocol Reference",
    description="HTTP documentation for room WebSocket messages. Standard Swagger UI does not open an interactive WebSocket connection.",
)
def websocket_protocol() -> dict:
    return {
        "connection": {
            "endpoint": "/ws/rooms/{room_code}/players/{player_id}",
            "example": "ws://127.0.0.1:8000/ws/rooms/1AS58K/players/1",
            "transport": "JSON messages over WebSocket",
        },
        "client_events": {
            "ping": {"type": "ping", "payload": {}},
            "secret_word_request": {"type": "secret_word_request", "payload": {}},
            "stroke_start": {"type": "stroke_start", "payload": {"stroke_id": "stroke-1", "x": 0.2, "y": 0.3, "color": "#222222", "width": 4, "tool": "pen"}},
            "stroke_point": {"type": "stroke_point", "payload": {"stroke_id": "stroke-1", "x": 0.25, "y": 0.35}},
            "stroke_end": {"type": "stroke_end", "payload": {"stroke_id": "stroke-1"}},
            "canvas_clear": {"type": "canvas_clear", "payload": {}},
            "canvas_sync_request": {"type": "canvas_sync_request", "payload": {}},
            "guess_submit": {"type": "guess_submit", "payload": {"guess": "waterfall"}},
        },
        "server_events": [
            "connection_established", "room_presence", "player_connected", "player_disconnected",
            "pong", "secret_word_assigned", "drawing_turn_started", "stroke_started", "stroke_point",
            "stroke_ended", "canvas_cleared", "canvas_state", "guess_received", "correct_guess",
            "leaderboard_updated", "round_started", "round_finished", "error",
        ],
        "rest_endpoints": {
            "start_drawing_turn": "POST /api/rooms/{room_code}/drawing/turn",
            "finish_round": "POST /api/rooms/{room_code}/rounds/finish",
            "next_round": "POST /api/rooms/{room_code}/rounds/next",
            "current_round": "GET /api/rooms/{room_code}/rounds/current",
            "leaderboard": "GET /api/rooms/{room_code}/leaderboard",
        },
        "rules": [
            "The server chooses the secret word and sends it only to the assigned drawer.",
            "The secret word is never included in public room, round, leaderboard, or guess responses.",
            "Players submit guesses over WebSocket with guess_submit.",
            "Correct guesses are scored once per player per round; earlier correct guesses receive a higher time-based score.",
            "The drawer cannot submit guesses.",
            "The host advances rounds with the REST next-round endpoint after the current round finishes or expires.",
            "Only the active drawer can draw or clear the canvas.",
            "Canvas coordinates are normalized numbers from 0 to 1; brush width is 1 to 40 and colors use #RRGGBB.",
            "Canvas history is process-local and bounded. Multi-worker deployments need shared state/pub-sub.",
            "Use Postman or the frontend to test WebSocket messages; Swagger documents REST endpoints and the protocol.",
        ],
    }
