# ACGS-Auth0 Web Demo

Live governance dashboard for the Auth0 Token Vault constitutional integration.

## Run locally

```bash
cd examples/governed_agents_web
pip install -r requirements.txt
python main.py
# → http://localhost:7860
```

## Deploy to Hugging Face Spaces (free, 1-click)

1. Create a new Space at https://huggingface.co/new-space
2. Choose SDK: **Gradio** (or Docker)
3. Upload this directory
4. The app starts on port 7860 automatically

## Deploy to Railway (free tier)

```bash
railway login
railway init
railway up
```

## Deploy to Render

1. Connect your GitHub repo
2. Set root directory: `examples/governed_agents_web`
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Governance dashboard UI |
| `GET /api/policy` | Constitutional policy (JSON) |
| `POST /api/check` | Validate token request |
| `POST /api/simulate` | Run preset scenario |
| `GET /api/audit` | Session audit trail |
| `GET /health` | Health check |
