# Doodle Party – Real-Time Multiplayer Drawing and Guessing Game

## Overview

Doodle Party is a browser-based multiplayer game where players take turns drawing a secret word while other players try to guess it. The backend uses WebSockets to support real-time drawing and guessing events.

## Features

- Create and join game rooms.
- Support multiple players in a room.
- Ready up and start a game.
- Draw and share drawing events in real time.
- Submit guesses and award points for correct answers.
- Rotate the drawer between rounds.
- View the leaderboard.
- Restart a finished room while keeping the same room and players.

## Technology Stack

### Backend
- Python 3.12
- FastAPI
- WebSockets
- SQLAlchemy
- Alembic
- MySQL 8.0

### Frontend
- React
- TypeScript
- Vite
- Material UI (MUI)
- Axios
- React Router

### Development Tools
- Docker and Docker Compose
- MySQL Workbench
- Postman
- Swagger / OpenAPI

## Project Structure

```text
MultiPlayer Game/
├── backend/
│   └── app/
│       ├── api/
│       ├── models/
│       ├── schemas/
│       └── services/
├── frontend/
├── docker-compose.yml
└── README.md
```

## Prerequisites

Install the following before running the project:

- Python 3.12
- Node.js and npm
- Docker Desktop
- Git (optional)

## Setup and Run

### 1. Configure Environment Variables

Create or update the `.env` file using the project's environment-variable template. Set the database connection and other required settings. Do not commit passwords, secret keys, or other sensitive values.

### 2. Start the Backend and Database

From the project root, run:

```bash
docker compose up -d --build
```

Check the containers:

```bash
docker compose ps
```

View backend logs if needed:

```bash
docker compose logs --tail 100 backend
```

### 3. Verify the Backend

Open these URLs in your browser:

- API documentation: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### 4. Start the Frontend

Open a separate terminal and move into the frontend directory:

```bash
cd frontend
npm install
npm run dev
```

Use the local URL printed by Vite in the terminal.

## Main API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/rooms` | Create a room |
| `GET` | `/api/rooms` | List rooms |
| `GET` | `/api/rooms/{room_code}` | Get room details |
| `POST` | `/api/rooms/{room_code}/join` | Join a room |
| `POST` | `/api/rooms/{room_code}/leave` | Leave a room |
| `PATCH` | `/api/rooms/{room_code}/ready` | Update player readiness |
| `POST` | `/api/rooms/{room_code}/start` | Start a game |
| `POST` | `/api/rooms/{room_code}/restart` | Restart a finished room |
| `POST` | `/api/rooms/{room_code}/drawing/turn` | Start a drawing turn |
| `GET` | `/api/rooms/{room_code}/rounds/current` | Get the current round |
| `POST` | `/api/rooms/{room_code}/rounds/finish` | Finish the current round |
| `POST` | `/api/rooms/{room_code}/rounds/next` | Start the next round |
| `GET` | `/api/rooms/{room_code}/leaderboard` | View scores |

## WebSocket

Connect a player using this URL pattern:

```text
ws://localhost:8000/ws/rooms/{room_code}/players/{player_id}
```

WebSocket messages use a JSON object with a `type` and a `payload`. For example, a drawing event may look like:

```json
{
  "type": "stroke_start",
  "payload": {
    "stroke_id": "stroke-1",
    "x": 0.2,
    "y": 0.3,
    "color": "#222222",
    "width": 4,
    "tool": "pen"
  }
}
```

Use the backend's supported event types and payload fields when sending drawing or guessing messages.

## Database and Migrations

Database schema changes are managed with Alembic. Apply migrations using the project's configured backend environment. For Docker-based setups, the command is typically:

```bash
docker compose exec backend alembic upgrade head
```

## Testing

- Use Swagger UI at `/docs` to test REST API endpoints.
- Use Postman to test WebSocket messages.
- Verify room status, round status, and player scores through the API.
- Check backend logs when an endpoint or WebSocket event returns an error.

## Notes

- Correct guesses award points according to the game rules.
- The drawer may receive a bonus when a player guesses correctly.
- Restarting a finished room resets it for a fresh game while preserving the room and player identities.
- Keep `.env` files and credentials private.

## License

Add the applicable license information here if the project is distributed publicly.
