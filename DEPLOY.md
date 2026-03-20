# Deployment Guide

## Docker Compose (local)

```bash
docker compose up -d
```

Backend: http://localhost:8000  
Health: http://localhost:8000/health  
Docs: http://localhost:8000/docs

## Render

1. Connect your Git repo to Render
2. Apply the `render.yaml` blueprint (New > Blueprint)
3. Add `OPENAI_API_KEY` in the dashboard (sync: false)
4. Deploy

The blueprint provisions: Postgres, Redis, and the backend web service.

## Railway

1. Create a new project and connect your repo
2. Add PostgreSQL from the Railway marketplace (optional; SQLite fallback if `DATABASE_URL` is unset)
3. Link `DATABASE_URL` to the Postgres service (or leave unset for SQLite)
4. Add `OPENAI_API_KEY` in variables
5. **Generate a public domain**: Settings → Networking → Generate Domain
6. Deploy

If the app is not accessible: ensure a public domain is generated and the deployment succeeded (check logs).

## Health checks

- **Liveness**: `GET /health` — basic app responsiveness
- **Readiness**: `GET /health/ready` — app + DB connectivity

## CORS

Set `CORS_ORIGINS` to your frontend URL(s), e.g. `https://your-app.onrender.com`. Use `*` for development only.
