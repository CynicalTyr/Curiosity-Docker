# START HERE

**If you only open one file, open this one.**

This is a first-use guide. It assumes you can log
into a Linux box, edit a text file, and paste commands. It does **not** assume
you already know Docker, MCP, or how AI agents call tools.

![Curiosity-Docker: a sidecar that finds public profile URLs for AI agents](docs/hero.png)

**One sentence:** Curiosity-Docker is a small Docker worker that answers
“does this public username show up on social sites, and at which URLs?” so an
AI agent does not have to scrape the web itself.

**Who it helps**

| Who | What they get |
| --- | --- |
| **You (the technician)** | A service you can start, health-check, and lock behind a key — without putting scrapers inside the AI. |
| **AI agents / harnesses** | Two tools: “is the worker up?” and “scan this handle.” They get JSON, not a browser. |
| **People talking to those agents** | Fewer invented profile links. The agent can *look up* a handle instead of guessing. |

It finds **candidate public URLs**. It does **not** prove that a person owns
that account. You still review results before treating them as identity.

---

## 0. Hero: what each file is for

Read this table once. You will come back to it when you edit things.

| File | What it does | What you change it for | How it helps agents / users |
| ---- | ------------ | ---------------------- | --------------------------- |
| `START_HERE.md` | This first-use guide | You usually do not | Humans: how to stand the worker up |
| `README.md` | Short product + hardware/software spec | When you document a fork | Humans: “is this the right tool?” |
| `docs/hero.png` | The banner picture | Branding only | Humans: 10-second mental model |
| `docs/HTTP_API.md` | Exact `/health` and `/scan` contract | If you add HTTP fields | Agents calling HTTP (no MCP) |
| `docs/MCP.md` | How MCP wraps that HTTP | If you add MCP tools | Chat/IDE agents that only speak MCP |
| `Dockerfile` | Recipe to **build** the image (Python + pinned lookup engine) | New base OS, new engine version | Reproducible worker; AGPL engine stays *in the image* |
| `docker-compose.yml` | How to **run** it on Linux (host network) | Ports, restart, env wiring | Live server / NAS next to an agent on the LAN |
| `docker-compose.bridge.yml` | How to **run** it on Docker Desktop (loopback only) | Laptop demos | Safer default: not exposed to the LAN |
| `shim_server.py` | Tiny HTTP server: API key, IP allowlist, one-scan lock | Timeouts, new JSON fields, extra routes | This is the door the agent knocks on |
| `.env.example` | List of setting **names** | Copy to `.env` (never commit `.env`) | Secrets stay off git |
| `examples/mcp_server.py` | MCP process the AI host launches | Tool names, timeouts | Lets Cursor / Claude Desktop / your harness call scans as tools |
| `examples/mcp.example.json` | Example MCP host config | Paths and env for *your* machine | Copy-paste into the harness |
| `examples/requirements-mcp.txt` | `pip` packages for the MCP process | MCP SDK version | Agent host only — not inside Docker |
| `scripts/smoke_health.sh` | One-command “is it alive?” | Default URL | First proof the live system works |
| `LICENSE.notice` | AGPL note for the engine inside the image | Legal, not ops | Do not copy the engine into the AI repo |

**Mental picture (same as the banner):**

```
User or agent  →  MCP tools  →  Docker HTTP sidecar  →  candidate profile URLs
                      │
                      └── examples/mcp_server.py talks HTTP to shim_server.py
```

The **Docker container** does the lookup. The **MCP file** is only a translator
so an AI harness can call that lookup as a tool. A locally built AI can skip
MCP and POST JSON itself.

---

## 1. What you need on the machine

- Linux with `docker` and `docker compose` (Compose v2: `docker compose version`).
- About **1.5 GiB** disk for the first image build, **1 GiB RAM** while a scan runs.
- Outbound HTTPS (the worker fetches public pages).
- **No GPU.** No Chrome.

Check:

```bash
uname -a
docker --version
docker compose version
```

If `docker compose` is missing, install Docker Engine + the Compose plugin from
your distro or Docker’s docs. You must be in the `docker` group (or use
`sudo`) so `docker ps` works without a lecture.

---

## 2. First run (practice on this box)

Do this on the computer that will **run the sidecar**. Ten minutes the first
time because it **builds** an image.

### 2.1 Get the files

```bash
git clone https://github.com/CynicalTyr/Curiosity-Docker.git
cd Curiosity-Docker
ls
```

You should see `docker-compose.yml`, `shim_server.py`, `Dockerfile`,
`START_HERE.md`.

### 2.2 Create secrets (never commit this file)

```bash
cp .env.example .env
nano .env          # or vim, or any editor
```

Set at least:

```
USERNAME_DISCOVERY_API_KEY=paste-a-long-random-string-here
USERNAME_DISCOVERY_ALLOWED_IPS=127.0.0.1
```

Make a key:

```bash
openssl rand -hex 32
```

Paste that hex into `USERNAME_DISCOVERY_API_KEY`. Save the file. **Do not**
put that string in git, tickets, or screenshots.

Same-machine agent (MCP on this box): leave allowlist `127.0.0.1`.  
Agent on **another** Linux box: put that box’s IP in
`USERNAME_DISCOVERY_ALLOWED_IPS` (comma-separated if more than one).

### 2.3 Start the worker

**Linux server / NAS:**

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail 30
```

**Docker Desktop (Mac/Windows) or if host networking is not available:**

```bash
docker compose -f docker-compose.bridge.yml up -d --build
```

Success looks like: container `curiosity-username-discovery` **running** /
**healthy**, logs mention the shim listening on port **8095**.

### 2.4 Health check (you should see JSON)

```bash
export USERNAME_DISCOVERY_API_KEY='the-same-key-as-in-.env'
./scripts/smoke_health.sh
```

Expected:

```json
{"status":"ok","mode":"fast"}
```

If you get `403`, the key is wrong or your IP is not allowlisted.  
If you get `connection refused`, the container is not listening — check
`docker compose ps` and logs.

### 2.5 Practice scan (optional, uses outbound HTTPS)

```bash
curl -sS -H "X-API-Key: $USERNAME_DISCOVERY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"username":"github","mode":"fast","top":5}' \
  http://127.0.0.1:8095/scan
```

You should get JSON with `"hits":[ ... ]` or `"hits":[]`. Empty hits still
mean **the scan finished**. That is normal.

A second `curl` while the first is still running may return
`{"error":"busy"}` with HTTP **503**. That is occupancy, not a crash. Wait,
then try again. **Do not** write a loop that retries 503 every 100 ms.

---

## 3. How to edit (safe daily work)

| You want to change… | Edit this | Then |
| ------------------- | --------- | ---- |
| API key or allowed IPs | `.env` | `docker compose up -d` (recreates with new env) |
| Listen port / timeout | `.env` and/or compose `environment:` | `docker compose up -d` |
| HTTP behavior (lock, JSON shape, extra route) | `shim_server.py` | File is **bind-mounted** — `docker compose restart` is enough |
| Base image or lookup-engine git SHA | `Dockerfile` | `docker compose build && docker compose up -d` |
| MCP tool names or client timeout | `examples/mcp_server.py` | Restart the **AI host** (not Docker), because MCP runs on the agent machine |

**Do not** edit files *inside* the container with `docker exec … vi`. Those
changes die when the container is recreated. Edit in this git directory.

After a shim edit, confirm:

```bash
docker compose restart
./scripts/smoke_health.sh
```

---

## 4. How to configure (the knobs that matter)

All names are in `.env.example`. Copy, then change **values** only in `.env`.

| Variable | Typical value | Meaning |
| -------- | ------------- | ------- |
| `USERNAME_DISCOVERY_API_KEY` | long random hex | Shared secret. Container, `curl`, and MCP must match. |
| `USERNAME_DISCOVERY_ALLOWED_IPS` | `127.0.0.1` or `10.0.0.5` | Who may call `/scan`. Use `*` **only** with the bridge compose (loopback publish). |
| `USERNAME_DISCOVERY_SCAN_TIMEOUT` | `60` | Seconds the **engine** may run inside Docker. |
| `USERNAME_DISCOVERY_URL` | `http://127.0.0.1:8095` | Used by smoke script and MCP — not required inside `.env` for Docker itself. |
| `USERNAME_DISCOVERY_TIMEOUT` | `120` | MCP/client wait. Keep this **larger** than scan timeout. |
| `USERNAME_DISCOVERY_TRUST_FORWARDED` | unset | Leave unset unless you know you have a reverse proxy. |

**Two compose files — pick one**

- `docker-compose.yml` — Linux, `network_mode: host`, real client IPs for the
  allowlist. Use this when the AI box is a **different** machine on a private
  LAN.
- `docker-compose.bridge.yml` — publishes `127.0.0.1:8095` only. Use this on a
  laptop. IP allowlist is weak through Docker’s proxy, so that file sets
  `ALLOWED_IPS=* ` and relies on the **key + loopback**.

Never publish port 8095 on the public internet.

---

## 5. Implement on a live system with an AI harness

An **AI harness** is the program that runs the model and its tools: Cursor,
Claude Desktop, VS Code Copilot Chat, or a custom MCP host. Those programs
do not speak Docker. They launch a **child process** (`examples/mcp_server.py`)
which then HTTP-calls your sidecar.

### 5.1 On the sidecar host (already done in §2)

Container healthy, key in `.env`, `./scripts/smoke_health.sh` returns `ok`.

### 5.2 On the agent / harness host (can be the same box)

```bash
# same git clone, or copy examples/ only
python3 -m pip install -r examples/requirements-mcp.txt
```

Copy `examples/mcp.example.json`. Change:

1. `args` → **absolute** path to `examples/mcp_server.py` on *this* machine.
2. `USERNAME_DISCOVERY_URL` → `http://127.0.0.1:8095` if sidecar is local,
   or `http://SIDECAR_IP:8095` if it is another host.
3. `USERNAME_DISCOVERY_API_KEY` → the same key as the sidecar `.env`.

Paste that block into the harness MCP config (Claude Desktop, Cursor
`mcp.json`, etc.). **Restart the harness.**

### 5.3 What “working” looks like in the harness

Ask the agent: “Call username discovery health.” You want JSON like
`{"status":"ok","mode":"fast"}`. Then: “Scan handle `github` with top 5.”
You want `hits` (maybe empty) — not a stack trace, not `403`, not `busy`
unless you already had a scan running.

If the harness says it has no such tool, the MCP process did not start:
check the absolute path, Python, and that **stdout is not used for logs**
(this adapter logs to stderr on purpose).

### 5.4 Teach the agent (short policy you can paste)

> Use username_discovery_health before a batch of scans. Scan one handle at a
> time. If the tool returns busy or timeout, stop the batch and wait for the
> next cycle. Hits are unverified public URLs — do not tell the user someone
> “definitely owns” that account. Do not retry busy in a tight loop.

---

## 6. Implement on a locally built AI (no MCP)

If you wrote your own agent in Python (or bash, or cron), you do **not** need
MCP. Your code is just an HTTP client.

### 6.1 Environment on the AI host

```bash
export USERNAME_DISCOVERY_URL=http://127.0.0.1:8095
export USERNAME_DISCOVERY_API_KEY='the-same-key-as-the-sidecar'
```

If the sidecar is another machine, use that host’s IP and put **this**
machine’s IP in the sidecar `USERNAME_DISCOVERY_ALLOWED_IPS`.

### 6.2 Health, then scan (copy into a worker)

```bash
# health
curl -sS -H "X-API-Key: $USERNAME_DISCOVERY_API_KEY" \
  "$USERNAME_DISCOVERY_URL/health"

# scan — wait up to 120s; sidecar scan cap is 60s
curl -sS -m 120 \
  -H "X-API-Key: $USERNAME_DISCOVERY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"username":"examplehandle","mode":"fast","top":10}' \
  "$USERNAME_DISCOVERY_URL/scan"
```

In Python, use `urllib` or `requests` the same way: header `X-API-Key`,
JSON body, timeout **120**. If status is 503, **return** from the job;
schedule the next run later (systemd timer, cron, or your loop’s next tick).

### 6.3 What to store

Save `hits[].url` and `hits[].platform` next to the handle you asked about.
Do **not** auto-mark them verified. Match the handle against the URL path
before you trust it. Empty `hits` means “we looked; nothing usable,” which is
still a completed pass.

---

## 7. Practice drills (do these once)

1. **Wrong key** — change `curl`’s key, expect `403`. Restore the key.
2. **Busy** — run two scans at once, expect one `busy`. Confirm the first
   still returns JSON.
3. **Edit shim** — add a log line in `shim_server.py`, `docker compose restart`,
   `docker compose logs --tail 20`, see your line. Revert if it was only a drill.
4. **Env change** — add a second IP to `ALLOWED_IPS`, `docker compose up -d`,
   confirm `docker compose exec` is unnecessary; env comes from `.env`.
5. **Stop** — `docker compose down`. Health check should fail. `up -d` brings
   it back. `.env` is still on disk.

---

## 8. When something is wrong

| Symptom | Likely cause | What to run |
| ------- | ------------ | ----------- |
| `permission denied` talking to Docker | User not in `docker` group | `groups`; log out/in after `usermod -aG docker $USER` |
| Image build fails on `git clone` | No outbound HTTPS / DNS | `curl -I https://github.com` from the host |
| Container restarts | Missing API key | `docker compose logs`; `.env` must contain `USERNAME_DISCOVERY_API_KEY=` |
| `403` | Key mismatch or IP not allowed | Compare `.env` to `export`; `curl` from the allowlisted host |
| `connection refused` | Not running, or wrong URL/port | `docker compose ps`; `ss -lntp \| grep 8095` |
| `busy` | Another scan holds the lock | Wait; do not hammer |
| MCP tools missing | Bad path or harness not restarted | Absolute path; Python can import `mcp` |
| Scan hangs 60s+ | Sites slow; timeout working | Client timeout must be **>** 60s |

---

## 9. What not to do

- Do not expose 8095 on a public WAN interface.
- Do not commit `.env`.
- Do not copy the lookup engine’s `app.py` into your AI repository (AGPL lives
  in the image — see `LICENSE.notice`).
- Do not treat a URL as “this is definitely that person.”
- Do not scan people who did not opt in, on your policy. This tool will not
  enforce your ethics file for you.

---

## 10. Where to go next

| Need | File |
| ---- | ---- |
| Hardware, software, security summary | [`README.md`](README.md) |
| Status codes and client “kinds” | [`docs/HTTP_API.md`](docs/HTTP_API.md) |
| MCP tools and host config | [`docs/MCP.md`](docs/MCP.md) |

You are done with first use when: container is healthy, smoke health returns
`ok`, and either a harness tool call **or** a `curl` scan returns JSON.
