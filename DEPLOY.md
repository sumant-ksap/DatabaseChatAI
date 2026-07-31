# Deploying DatabaseChatAI to Render

This app runs as a single Docker container: Ollama and the Flask app both run
inside it. `entrypoint.sh` starts `ollama serve`, pulls the configured model,
then starts the web app with gunicorn.

## 1. Push to GitHub

```
git remote add origin https://github.com/sumant-ksap/DatabaseChatAI.git
git push -u origin main
```

If the remote already has commits (e.g. a README created on github.com), pull
first: `git pull --rebase origin main`, resolve anything, then push.

## 2. Create the Render service

1. Go to https://dashboard.render.com → **New** → **Blueprint**.
2. Connect your GitHub account/repo if you haven't already, then pick
   `sumant-ksap/DatabaseChatAI`.
3. Render reads `render.yaml` from the repo root and proposes one service:
   `databasechatai` (Docker runtime, plan `pro`, 20GB disk mounted at `/data`).
4. Review and click **Apply** to create it.

If you'd rather not use the Blueprint, you can instead click **New → Web
Service**, point it at the repo, and it will auto-detect the `Dockerfile`.
In that case add the disk and env vars from `render.yaml` manually in the
service's **Disks** and **Environment** tabs.

## 3. Sizing (important)

`gemma4:e4b` is a multi-GB model that Ollama loads into RAM. The `render.yaml`
here defaults to the **Pro** plan as a safe starting point — adjust up/down
in the Render dashboard once you see actual memory usage in the service's
**Metrics** tab. Free/Starter plans (512MB–2GB RAM) will very likely OOM.

The attached disk (`/data`, 20GB) caches the pulled model so redeploys and
restarts don't re-download it every time — without a disk, every restart
re-pulls the model and cold-starts slowly.

## 4. First boot

The first deploy will take several minutes longer than normal: Ollama has to
pull the model before gunicorn starts answering requests. Watch the **Logs**
tab — you should see `Pulling model gemma4:e4b...` followed by `Starting web
app on port ...`. Render's health check will show the service as up only
once gunicorn is listening.

## 5. Using the app

Once deployed, Render gives you a public URL
(`https://databasechatai.onrender.com` or similar). Anyone with that URL can
open it and connect their own PostgreSQL/MongoDB credentials through the
in-app connection form — credentials are only held in server memory for that
session, not stored in the repo or env vars.

## Environment variables

| Variable          | Default                     | Purpose                              |
|--------------------|------------------------------|---------------------------------------|
| `OLLAMA_MODEL`      | `gemma4:e4b`                | Model Ollama pulls and serves         |
| `OLLAMA_BASE_URL`   | `http://127.0.0.1:11434`    | Where agent.py reaches Ollama         |
| `OLLAMA_MODELS`     | `/data/ollama-models`        | Where Ollama stores pulled models     |
| `PORT`              | set by Render automatically | Port gunicorn binds to                |

## Local development

Local runs are unaffected — with no env vars set, `agent.py` still defaults
to `http://127.0.0.1:11434` and `app.py` still defaults to port 5000, so your
existing local Ollama workflow keeps working as before.
