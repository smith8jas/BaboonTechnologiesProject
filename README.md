# BaboonTechnologiesProject

Basic full-stack project scaffold.

## Structure

- `frontend/`: static frontend starter
- `backend/`: Python FastAPI backend managed with `uv`

## Backend

```sh
cd backend
uv run uvicorn backend.main:app --reload
```

API health check:

```sh
curl http://127.0.0.1:8000/health
```

## Frontend

Open `frontend/index.html` in a browser. It will check the backend health endpoint when the API is running.
