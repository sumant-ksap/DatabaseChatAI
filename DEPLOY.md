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
   `databasechatai` (Docker runtime, plan `free`).
4. Review and click **Apply** to create it.

If you'd rather not use the Blueprint, you can instead click **New → Web
Service**, point it at the repo, and it will auto-detect the `Dockerfile`.

## 3. Sizing (important — read this if the deploy fails)

`render.yaml` is currently set to the **Free** plan so it deploys with no
payment info required. Be aware this is very likely **not enough to actually
run the app**: `gemma4:e4b` is a multi-GB model that Ollama loads into RAM,
and Free gives only 512MB with no disk. Expect the container to be OOM-killed
on startup, or the model to never finish pulling before Render's health check
times out.

Free also has no disk, so `OLLAMA_MODELS` points at a path on the
container's own ephemeral filesystem — even if it did start successfully,
every restart or spin-down (Free services sleep after 15 min idle) would
force a full model re-download.

If you hit exactly this failure in the Logs tab, the fix is to move to a
paid plan (`pro` is what this file used before, with a 20GB disk mounted at
`/data` for the model) — see the git history of this file for that config —
or swap the app to call a hosted LLM API instead of local Ollama, which
would let Free actually work.

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
