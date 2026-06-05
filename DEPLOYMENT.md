# Deployment

This app is designed to run as two hosted services:

- Frontend: Vercel, root directory `frontend`
- Backend: Render, root directory `backend`

## Backend on Render

Create a Render Web Service from this repository. You can use `render.yaml` as a blueprint, or configure manually:

```bash
Build Command: pip install uv && uv sync --frozen
Start Command: uv run uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Set these environment variables in Render:

```env
APP_NAME=Baboon Technologies API
ENVIRONMENT=production
CORS_ORIGINS=https://your-vercel-frontend-url.vercel.app
EDGAR_USER_AGENT=your_email@example.com
FRED_API_KEY=your_fred_api_key
OPENAI_API_KEY=your_openai_api_key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
```

## Frontend on Vercel

Create a Vercel project from this repository:

```text
Root Directory: frontend
Build Command: npm run build
Output Directory: dist
```

Set this environment variable in Vercel:

```env
VITE_API_BASE_URL=https://your-render-backend-url.onrender.com
```

After both deploys finish, update `CORS_ORIGINS` in Render with the final Vercel URL and redeploy the backend.
