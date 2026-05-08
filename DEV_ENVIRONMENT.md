# Development Environment Guide

> **Quick reference for docker, testing, access credentials, and development setup**

**Last Updated**: 2026-03-28

---

## 🐳 Docker Setup

### Quick Start

```bash
Check if dev container is running by name fdocker_devcontainer-frappe-1 or id 54de6991a349e8bdf93c0fc69b10f4e4bdd89bc98ff1ab55f05fd9e6b737a132 this is part of dev container and located boot from  /Users/safwan/Code/docker/fdocker/ using config /Users/safwan/Code/docker/fdocker/.devcontainer/docker-compose.yml

the bench in it is located in /Users/safwan/Code/docker/fdocker/development/edge16/

And app is at /Users/safwan/Code/docker/fdocker/development/edge16/apps/huf

You need to connect to this container to and run the following commands :
bench use huf.localhost
bench start 
bench migrate

etc.. 

However code you can edit in the host and it is same as on the container.

```

Site credentials:
**Access**: http://localhost:8000  
**Credentials**: `Administrator` / `admin`



### Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| **MariaDB** | mariadb:10.11 | 3306 (internal) | Database |
| **Redis** | redis:alpine | 6379 (internal) | Cache/Queue |
| **Frappe** | frappe/bench:latest | 8000, 9000 | App Server |

### Docker Environment Variables

| Variable | Value | Description |
|----------|-------|-------------|
| `MYSQL_ROOT_PASSWORD` | 123 | MariaDB root password |
| `HUF_BRANCH` | develop | Git branch to checkout  or whaever you are working on|
| `UV_HTTP_TIMEOUT` | 300 | UV package manager timeout |


## 🔑 Access Credentials
**Access**: http://localhost:8000  
**Credentials**: `Administrator` / `admin`



### Default Login

| Environment | URL | Username | Password |
|-------------|-----|----------|----------|
| **Docker** | http://localhost:8000 | `admin` | `admin` |
| **Dev Container** | http://localhost:8101 | `Administrator` | `admin` |

Note: port can change based on bench start response and could be localhost:8000, or localhost:8001 or localhost:8002 etc.


### API Authentication

Most API calls require cookies from login. See test scripts for examples:

```bash
# Login and save cookies
curl -c cookies.txt -X POST http://localhost:8101/api/method/login \
  -d 'usr=Administrator' \
  -d 'pwd=admin'

# Use cookies for subsequent calls
curl -b cookies.txt http://localhost:8101/api/method/frappe.ping
```

---

## 🧪 Testing

### Backend Tests

```bash
# Run all tests
bench --site huf.localhost run-tests --app huf

# Run specific test file
bench --site huf.localhost run-tests --app huf --module agent
```

### Frontend Tests

```bash
cd frontend

# Type checking
yarn typecheck

# Linting
yarn lint

# Build (catches TypeScript errors)
yarn build
```

### Manual Testing Scripts

| Script | Purpose | Location |
|--------|---------|----------|
| `test_backend_core.py` | Backend API tests | Root |
| `test_authenticated_flows.py` | Auth + Flow API tests | Root |
| Playwright scripts | UI automation | `/tmp/test_*.py` |

### Browser automation (Docker Chrome, Browserless, or host Chrome)

You can drive the UI with **Playwright**, **Puppeteer**, **Browserless**, or **IDE browser MCP** (e.g. Cursor). Pick either a **headless/browser service in Docker** (reachable from the host via a published port) or **Chrome/Chromium on the host**.

#### Option A — Containerized browser (Browserless, Playwright Docker, etc.)

- Run an image that exposes Chrome or a CDP/WebSocket endpoint, and **publish a port** to the host (for example `3000` for Browserless, or the port your stack documents).
- Automation that runs **on the host** connects to `localhost` on that port (e.g. `ws://127.0.0.1:<port>/...` or the provider’s HTTP API).
- In tests, open the app using the same URLs you use in a normal browser: Frappe on Docker is usually `http://localhost:8000` or `http://huf.localhost:8000` (see site name); Vite-only dev is `http://localhost:8080`.

Example (Browserless-style; adjust image and flags to match your version):

```bash
docker run -p 3000:3000 ghcr.io/browserless/chromium
# Host automation connects to localhost:3000 per Browserless docs
```

#### Option B — Host Chrome / Chromium

- **Playwright**: install browsers with `python -m playwright install chromium` (bundled Chromium) or use a system/Chrome install where supported (`channel: "chrome"`).
- **IDE tools**: browser MCP typically drives **Chrome on the host** against those same `localhost` / `huf.localhost` URLs.

#### Networking quick reference

| Where the test runs | Where Frappe runs | Base URL to use |
|---------------------|-------------------|-----------------|
| Host | Docker, port mapped | `http://localhost:8000` or `http://huf.localhost:8000` |
| Linux container | Frappe on host | `http://host.docker.internal:8000` (or host gateway IP) |
| Same Docker network as Frappe | Frappe container | Service name + internal port (e.g. `http://frappe:8000`) |

### Browser Testing with Playwright (host install)

```bash
# Install Playwright
pip install playwright
python -m playwright install chromium

# Run test (example)
python /tmp/test_flow_ui.py
```

---

## 🌐 Ports & URLs

### Development Environment

| Service | URL | Port | Notes |
|---------|-----|------|-------|
| **Frappe App** | http://localhost:8000 | 8000 | Docker environment |
| **Dev Container** | http://localhost:8101 | 8101 | VS Code devcontainer |
| **Frontend Dev** | http://localhost:8080 | 8080 | Vite dev server |
| **Socket.io** | ws://localhost:9000 | 9000 | Real-time chat |
| **Browserless / CDP** | `localhost` | *varies* | Publish when using Docker Chrome; connect from host or containers per table above |

### Backend API Endpoints

| Endpoint | URL | Method |
|----------|-----|--------|
| Ping | `/api/method/frappe.ping` | GET |
| Login | `/api/method/login` | POST |
| Get Flow | `/api/method/huf.ai.flow_api.get_flow_definition` | GET |
| Save Flow | `/api/method/huf.ai.flow_api.save_flow_definition` | POST |
| Run Flow | `/api/method/huf.ai.flow_api.run_flow` | POST |


### Option 4: Bench inside Docker / devcontainer (edge16)

The Flow UI is also tested **from Frappe** while `bench start` runs inside the container. In that layout the bench root and app path are fixed:

| Item | Path (inside container) |
|------|-------------------------|
| Bench root | `/workspace/development/edge16` |
| HUF app | `/workspace/development/edge16/apps/huf` |

```bash
cd /workspace/development/edge16
bench start
```

Use the site URL and credentials for that environment (often the devcontainer row in [Access Credentials](#-access-credentials)). Socket.io and API follow that host/port, not Vite’s 8080.

#### Host clone vs `apps/huf` (git sync)

Edits in a **host checkout** of this repo (for example opened in Cursor on your Mac) are **not** the same working tree as `/workspace/development/edge16/apps/huf` unless that directory is a bind mount of your clone. If they are separate clones, you must **push from the host and pull in the bench app** (or the reverse) to see changes where `bench` runs.

**Workflow**

1. On the host: commit, `git push` your branch.
2. Where bench runs (devcontainer shell or `docker exec`):
   ```bash
   cd /workspace/development/edge16/apps/huf
   git fetch origin
   git checkout <your-branch>
   git pull
   ```
3. After **frontend** changes, rebuild assets so Frappe serves the new UI:
   ```bash
   cd /workspace/development/edge16/apps/huf/frontend
   yarn install   # if dependencies changed
   yarn build
   ```
   Or from the bench root: `bench build --app huf` (builds app assets per Frappe).

4. For **Python** changes, restart workers if needed (`bench restart` or restart the relevant processes).

---

## 📝 Frontend Development

### Build Commands

```bash
cd frontend

# Install dependencies
yarn install

# Dev server (localhost:8080)
yarn dev

# Production build
yarn build

# Type check
yarn typecheck

# Lint
yarn lint
```

### Build Output

Frontend builds to `huf/public/frontend/` which is served by Frappe.

---

## 🐛 Debugging

### Browser Console

Check for these common errors:

| Error | Meaning | Fix |
|-------|---------|-----|
| `React error #130` | Undefined component | Check icon imports |
| `React error #185` | Infinite loop | Check useEffect deps |
| `WebSocket failed` | Socket.io connection | Check port 9000/9001 |
| `403 Forbidden` | Auth issue | Re-login |

### Backend Logs

```bash
# Docker
docker compose logs -f frappe

# Bench
bench --site huf.localhost serve
```

### Frontend Logs

```bash
# Dev server
yarn dev

# Browser DevTools → Console
```

---

## 📁 Key Directories

| Path | Purpose |
|------|---------|
| `/workspace/development/edge16/` | Bench root (`bench start` here) |
| `/workspace/development/edge16/apps/huf/` | HUF app inside that bench (pull after host push) |
| `/workspace/development/edge16/sites/huf.localhost/` | Site data (name may differ per site) |
| `huf/huf/doctype/` | Backend DocTypes |
| `frontend/src/` | Frontend source |
| `screenshots/` | Test screenshots |

---

## 🔧 Common Issues

### Port 8000 Already in Use

```bash
# Find process
lsof -i :8000

# Kill or use different port
docker compose -f docker-compose.yml -p huf2 up
```

### Database Connection Failed

```bash
# Check MariaDB
docker compose ps
docker compose logs mariadb

# Reset (WARNING: deletes data)
docker compose down -v
docker compose up
```

### Frontend Build Fails

```bash
# Clear cache
rm -rf frontend/node_modules
rm -rf frontend/.vite
yarn install
yarn build
```

---

## 📚 Related Documentation

| Document | Purpose |
|----------|---------|
| [INDEX.md](INDEX.md) | Master navigation index |
| [CLAUDE.md](CLAUDE.md) | Project architecture |
| [FLOW_UI_FEATURE_TRACKER.md](FLOW_UI_FEATURE_TRACKER.md) | Feature status |
| [FLOW_NODE_MODAL_TRACKER.md](FLOW_NODE_MODAL_TRACKER.md) | Modal status |

---

*Update this guide when environment changes.*
