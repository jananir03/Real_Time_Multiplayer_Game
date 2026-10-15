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


## Setup and Run

### 1. Start the Backend and Database

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

### 2. Verify the Backend

Open these URLs in your browser:

- API documentation: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### 3. Start the Frontend

Open a separate terminal and move into the frontend directory:

```bash
cd frontend
npm install
npm run dev
```

