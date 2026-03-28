# Development Environment Guide

> **Quick reference for docker, testing, access credentials, and development setup**

**Last Updated**: 2026-03-28

---

## 🐳 Docker Setup

### Quick Start

```bash
cd docker
docker compose up
```

**Access**: http://localhost:8000  
**Credentials**: `admin` / `admin`

> ⚠️ **First run takes 5-8 minutes** for initial setup

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
| `HUF_BRANCH` | develop | Git branch to checkout |
| `UV_HTTP_TIMEOUT` | 300 | UV package manager timeout |

### Useful Docker Commands

```bash
# Start services
docker compose up -d

# View logs
docker compose logs -f frappe

# Restart service
docker compose restart frappe

# Shell into container
docker exec -it huf-frappe-1 bash

# Stop all
docker compose down
```

---

## 🔑 Access Credentials

### Default Login

| Environment | URL | Username | Password |
|-------------|-----|----------|----------|
| **Docker** | http://localhost:8000 | `admin` | `admin` |
| **Dev Container** | http://localhost:8101 | `Administrator` | `admin` |

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

### Browser Testing with Playwright

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

### Backend API Endpoints

| Endpoint | URL | Method |
|----------|-----|--------|
| Ping | `/api/method/frappe.ping` | GET |
| Login | `/api/method/login` | POST |
| Get Flow | `/api/method/huf.ai.flow_api.get_flow_definition` | GET |
| Save Flow | `/api/method/huf.ai.flow_api.save_flow_definition` | POST |
| Run Flow | `/api/method/huf.ai.flow_api.run_flow` | POST |

---

## 💻 Development Setup

### Option 1: Docker (Recommended for Quick Start)

```bash
cd docker
docker compose up
# Access: http://localhost:8000 (admin/admin)
```

### Option 2: Frappe Bench (Full Development)

```bash
# 1. Install Frappe bench
pip install frappe-bench

# 2. Create bench
bench init frappe-bench

# 3. Get HUF app
cd frappe-bench
bench get-app huf <repo-path>

# 4. Create site
bench new-site huf.localhost

# 5. Install app
bench --site huf.localhost install-app huf

# 6. Start services
bench start
```

### Option 3: VS Code Dev Container

1. Open project in VS Code
2. Click "Reopen in Container"
3. Wait for container setup
4. Access at http://localhost:8101

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
| `/workspace/development/edge16/apps/huf/` | Devcontainer app path |
| `/workspace/development/edge16/sites/huf.localhost/` | Site data |
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
