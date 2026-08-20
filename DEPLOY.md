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

## 3. Cloud model auth (important — read this if chat requests 401)

`OLLAMA_MODEL` is set to `gemma4:31b-cloud`. Unlike `gemma4:e4b`, this model
doesn't run inside the container at all — Ollama just proxies inference
requests to Ollama's cloud servers. That means Render's Free plan (512MB RAM,
no disk) is no longer the bottleneck for this model. **Authentication is.**

`ollama pull gemma4:31b-cloud` only fetches a small remote-pointer manifest,
so the container boots and the deploy succeeds even with no identity —
the failure shows up later, at chat time, when the daemon actually proxies
a request to `ollama.com` and gets back `401 Unauthorized` because it isn't
signed in to any account.

The fix is `OLLAMA_API_KEY`, Ollama Cloud's headless-auth env var (an
alternative to the interactive `ollama signin` flow, which needs a browser
and isn't practical in a container):
1. Generate a key at https://ollama.com/settings/keys.
2. In Render → this service → **Environment**, set `OLLAMA_API_KEY` to that
   value (it's declared in `render.yaml` with `sync: false`, so Render will
   prompt for it there rather than storing it in the repo).
3. Redeploy. `entrypoint.sh` starts `ollama serve` as a child process, which
   inherits the container's env vars automatically — no script change needed
   for the daemon to pick up the key.

This repo deliberately does **not** bake any key into the Docker image or
commit one to git — that would leak a credential tied to a personal Ollama
account into a public repo and Render's build logs.

Fallback: `gemma4:e4b` runs in-container with no auth requirement, just a
RAM/disk one — see this file's git history for the paid-plan config that
supports it.

## 4. First boot

The first deploy will take several minutes longer than normal: Ollama has to
pull the model before gunicorn starts answering requests. Watch the **Logs**
tab — you should see `Pulling model gemma4:31b-cloud...` followed by
`Starting web app on port ...`. Render's health check will show the service
as up only once gunicorn is listening.

## 5. Using the app

Once deployed, Render gives you a public URL
(`https://databasechatai.onrender.com` or similar). Anyone with that URL can
open it and connect their own PostgreSQL/MongoDB credentials through the
in-app connection form — credentials are only held in server memory for that
session, not stored in the repo or env vars.

## Environment variables

| Variable          | Default                     | Purpose                              |
|--------------------|------------------------------|---------------------------------------|
| `OLLAMA_MODEL`      | `gemma4:31b-cloud`          | Model Ollama pulls and serves         |
| `OLLAMA_BASE_URL`   | `http://127.0.0.1:11434`    | Where agent.py reaches Ollama         |
| `OLLAMA_MODELS`     | `/data/ollama-models`        | Where Ollama stores pulled models     |
| `OLLAMA_API_KEY`    | none — must be set manually | Auth for `gemma4:31b-cloud` inference; get one at https://ollama.com/settings/keys |
| `PORT`              | set by Render automatically | Port gunicorn binds to                |

## Local development

Local runs are unaffected — with no env vars set, `agent.py` still defaults
to `http://127.0.0.1:11434` and `app.py` still defaults to port 5000, so your
existing local Ollama workflow keeps working as before.
