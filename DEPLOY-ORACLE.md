# Deploying DatabaseChatAI to Oracle Cloud (Always Free)

Render's free plan can't run Ollama (no disk, 512MB RAM). Oracle Cloud's
**Always Free** tier gives a real VM — up to 4 OCPUs / 24GB RAM (Ampere A1,
ARM) — at no cost, forever, as long as you stay within Always Free limits.
This guide runs the same Docker setup from this repo directly on that VM.

Steps 1-3 have to happen in your browser — I can't sign up for Oracle or
click through their console for you. Once the VM exists and you can SSH into
it, share the public IP and I can run steps 4+ for you directly.

## 1. Create an Oracle Cloud account

1. Go to https://signup.oraclecloud.com and sign up for the **Always Free**
   tier.
2. Oracle requires a credit card for identity verification during signup.
   Resources tagged "Always Free" are never billed as long as you don't
   exceed their limits — but keep an eye on what you provision.

## 2. Create the Always Free compute instance

1. In the OCI Console: **Compute → Instances → Create Instance**.
2. Name it (e.g. `databasechatai`).
3. Under **Image and shape**, click **Edit**:
   - Image: **Canonical Ubuntu 22.04** (or latest 22.04/24.04).
   - Shape: click **Change shape**, choose **Ampere** → **VM.Standard.A1.Flex**,
     which is marked "Always Free eligible." Set OCPUs/memory up to the
     Always Free limit (e.g. 4 OCPU / 24GB, or split across multiple free
     VMs if you prefer).
4. Under **Add SSH keys**, either generate a new key pair (download the
   private key) or paste your own public key. You'll need the private key to
   SSH in.
5. Leave networking as default (it creates a public subnet + public IP).
6. Click **Create**. Wait for the instance state to become **Running**, then
   note its **Public IP**.

## 3. Open the firewall for the app's port

Oracle blocks inbound traffic by default at two layers — both need an
opening for whatever port the app will be reachable on (this guide uses 80):

1. **Security List / Network Security Group**: Networking → Virtual Cloud
   Networks → your VCN → the subnet used by the instance → its Security List
   → **Add Ingress Rules**: source `0.0.0.0/0`, destination port `80`,
   protocol TCP.
2. **VM's own firewall (iptables)**: Ubuntu images on OCI ship with iptables
   rules blocking most inbound ports by default — this gets opened from
   inside the VM in step 5 below.

## 4. SSH in and install Docker

From your machine:

```
ssh -i /path/to/private_key ubuntu@<PUBLIC_IP>
```

Once connected:

```
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# also open the VM's own iptables for port 80
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || sudo apt-get install -y iptables-persistent
```

## 5. Clone the repo and run the container

```
git clone https://github.com/sumant-ksap/DatabaseChatAI.git
cd DatabaseChatAI
sudo docker build -t databasechatai .
sudo docker run -d --name databasechatai --restart unless-stopped \
  -p 80:80 -e PORT=80 \
  -v /opt/ollama-models:/data/ollama-models \
  databasechatai
```

- `-p 80:80 -e PORT=80` exposes the app on the VM's public IP at port 80
  (`http://<PUBLIC_IP>/`).
- `-v /opt/ollama-models:/data/ollama-models` persists the pulled model on
  the VM's own disk, so `docker restart` / VM reboots don't re-download it.
- `--restart unless-stopped` brings the container back up automatically if
  the VM reboots.

First start will take a while — Ollama has to pull the model before the app
answers requests. Check progress with:

```
sudo docker logs -f databasechatai
```

You're looking for `Pulling model gemma4:e4b...` followed by `Starting web
app on port 80...`.

## 6. Using the app

Once it's up, `http://<PUBLIC_IP>/` is reachable by anyone. Each user
connects their own PostgreSQL/MongoDB credentials through the in-app
connection form — credentials only live in server memory for that session.

Optional next steps, not required to get it working:
- Point a domain name at `<PUBLIC_IP>` and put a reverse proxy (e.g. Caddy)
  in front for free HTTPS, since the raw IP setup above is HTTP-only.
- Reserve the public IP in the OCI Console so it doesn't change if the
  instance restarts (ephemeral IPs can change; reserved ones don't).

## Redeploying after code changes

```
cd DatabaseChatAI
git pull
sudo docker build -t databasechatai .
sudo docker stop databasechatai && sudo docker rm databasechatai
sudo docker run -d --name databasechatai --restart unless-stopped \
  -p 80:80 -e PORT=80 \
  -v /opt/ollama-models:/data/ollama-models \
  databasechatai
```
