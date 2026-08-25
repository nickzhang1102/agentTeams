# Agent Teams System

> A team-oriented multi-agent collaboration platform built on Vue3+Vite and FastAPI, featuring SSE real-time streaming chat, agent teamwork, and Leader intelligent orchestration (LangGraph).
>
> 🌐 **Live demo site**: [https://nickzhang1102.github.io/agentTeams/](https://nickzhang1102.github.io/agentTeams/)

[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-20.19+-green.svg)](https://nodejs.org/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-18-blue.svg)](https://www.postgresql.org/)

English | [简体中文](./README.md)

## 🎯 Features

### Core
- ✅ **JWT authentication** - Secure user registration & login
- ✅ **SSE streaming chat** - Real-time AI conversation experience
- ✅ **Markdown rendering** - Rich text display with code highlighting
- ✅ **File management** - Upload / download / preview / versioning
- ✅ **Conversation management** - CRUD, archiving, sharing
- ✅ **Knowledge graph** - D3 visualization, GraphRAG retrieval, gap analysis

### Agent system
- ✅ **100+ built-in expert agents** - Covering medical specialties, business roles, financial futures, and more
- ✅ **Agent teamwork** - Parallel execution with intelligent aggregation
- ✅ **Leader Agent** - Requirement assessment, team formation (DAG orchestration), result synthesis
- ✅ **AgentPack / workflow templates** - Agent bundle management and one-click launch templates

### UI enhancements
- ✅ **Dark mode** - One-click theme switching
- ✅ **Export** - PDF / image export
- ✅ **i18n** - Chinese / English interface
- ✅ **Admin console** - Agent editing, tool configuration, performance monitoring

## 🔒 Security

- Authentication via JWT + httpOnly Cookie (SameSite=Strict)
- Passwords hashed with pbkdf2 + RSA-encrypted transmission
- Mandatory secret validation at startup (`SECRET_KEY` / `JWT_SECRET_KEY` — refuses to boot if missing or too weak)
- For public self-hosted deployments, always set `APP_ENV=production` and change default credentials

## 🚀 Quick Start

### Option 1: Docker deployment (recommended)

```bash
# 1. Clone the project
git clone https://github.com/nickzhang1102/agentTeams.git
cd agentTeams

# 2. Configure environment variables
cp backend/.env.example backend/.env
# Edit backend/.env to set database and root secrets; add LLM models in the admin console after startup

# 3. One-click deployment
# Linux/macOS:
./scripts/docker-deploy.sh

# Windows (PowerShell):
.\scripts\docker-deploy.ps1

# 4. Access the app
# Frontend: http://localhost:8380
# Admin account: admin — the initial password is randomly generated;
#            see `docker compose logs backend` or the host file
#            backend/data/.admin_initial_password
#           (admin/admin123 only applies to local development with APP_ENV=development).
#            Change the password immediately after first login.
```

See also: [Docker deployment guide](./DOCKER.md) (Chinese)

### Option 2: Local development

#### Prerequisites
- Node.js 20.19+ (required by Vite 8)
- Python 3.11+
- PostgreSQL 18
- An OpenAI-compatible LLM service account (configured in the admin console after startup)

#### Backend

```bash
cd backend

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install the bundled OpenHarness framework (required for local dev; handled automatically in Docker)
pip install -e ../OpenHarness

# Configure environment variables
cp .env.example .env
# Edit .env to set DATABASE_URL, SECRET_KEY, and JWT_SECRET_KEY

# Initialize the database
alembic upgrade head

# Create the default admin account (default password admin123 — change it immediately after first login)
python init_admin.py

# Start the server
python run.py
```

LLM models are configured in the admin console under "LLM Models"; Exa/Tavily keys under "System Settings". Database credentials are encrypted with `SECRET_KEY`; before rotating that root key you must decrypt and re-encrypt the stored credentials with the old key, otherwise the service will refuse to read them.

> Note: `init_admin.py` only uses the default password when `APP_ENV=development` is explicitly set (as in `.env.example`). Without it, a random password is generated and printed.

#### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Configure environment variables
cp .env.example .env

# Start the dev server
npm run dev
```

Visit http://localhost:5173

See also: [Quick start guide](./QUICKSTART.md) (Chinese)

## 📁 Project structure

```
agentTeams/
├── backend/              # FastAPI backend
│   ├── app.py           # Application factory
│   ├── models.py        # Data models
│   ├── api/             # RESTful routes
│   ├── services/        # Domain services
│   ├── leader/          # LangGraph orchestration layer
│   └── tests/           # Tests
│
├── frontend/            # Vue3 frontend
│   ├── src/
│   │   ├── views/      # Page components
│   │   ├── components/ # UI components
│   │   ├── stores/     # Pinia state management
│   │   └── locales/    # i18n messages
│   └── e2e/             # Playwright E2E tests
│
├── OpenHarness/          # Bundled agent execution framework (MIT)
│
├── .claude/              # Agent configuration
│   └── agents/         # Built-in expert agent definitions
│
├── docker/              # Docker configuration
│   └── init-db.sql     # Database initialization
│
├── scripts/             # Deployment scripts
│   ├── docker-deploy.sh
│   └── docker-deploy.ps1
│
├── website/             # GitHub Pages site
│   ├── index.html      # Single-page site (light tech-blue theme)
│   └── sponsor/        # Sponsorship QR codes
│
├── docker-compose.yml   # Docker Compose configuration
├── DOCKER.md           # Docker guide (Chinese)
└── QUICKSTART.md       # Quick start (Chinese)
```

> `OpenHarness/` is a bundled third-party subproject licensed under MIT (upstream OpenHarness project), installed via `pip install -e`.

## 🛠️ Tech stack

### Backend
- **FastAPI** - Web framework
- **SQLAlchemy 2.0** - ORM
- **PostgreSQL 18** - Database (pgvector index)
- **LangGraph** - Multi-agent orchestration
- **psycopg 3.3** - PostgreSQL driver
- **python-jose** - JWT authentication
- **OpenAI SDK** - LLM API integration (OpenAI-compatible)

### Frontend
- **Vue 3.4** - UI framework
- **Vite 8** - Build tool
- **Pinia** - State management
- **Element Plus** - UI component library
- **D3.js** - Knowledge graph visualization
- **Marked** - Markdown parsing

### Deployment
- **Docker** - Containerization
- **Docker Compose** - Service orchestration
- **Nginx** - Frontend server
- **Uvicorn / Gunicorn** - ASGI server

## 🔌 API endpoints (excerpt)

### Auth
- `POST /api/auth/register` - Register
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Current user

### Conversations
- `GET /api/conversations` - List conversations
- `POST /api/conversations` - Create conversation
- `GET /api/conversations/:id` - Conversation detail
- `PUT /api/conversations/:id` - Update conversation
- `DELETE /api/conversations/:id` - Delete conversation

### Agents & teams
- `GET /api/agents` - List agents

### Leader & workflows
- `POST /api/leader/start` - Start a Leader session
- `GET /api/agent-packs` - List agent packs
- `POST /api/workflow-templates/{id}/apply` - Apply a workflow template to launch instantly

## 🧪 Testing

### Backend

> **Prerequisites**: PostgreSQL 18 must be running locally, and a dedicated test database must exist:
>
> ```sql
> CREATE DATABASE agent_teams_test;
> ```
>
> Full details are documented in the comments at the top of `backend/.env.example` (`TEST_DATABASE_URL`).

```bash
cd backend

# Run all tests
python -m pytest tests/ -v
```

### Frontend

```bash
cd frontend

# Unit tests (Vitest)
npm run test

# E2E tests (Playwright)
npm run test:e2e

# Build verification
npm run build
```

> **E2E prerequisites**:
> - A full backend service must be running (API reachable);
> - Run `npx playwright install chromium` before first use;
> - The admin suite requires an account manually promoted to administrator and not locked out, provided via the `E2E_ADMIN_USER` / `E2E_ADMIN_PASSWORD` environment variables (defaults are for local E2E only).

## 📝 Environment variables

### Backend (`.env`)

```bash
# Required infrastructure settings
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agent_teams

# LLM and Exa/Tavily credentials are configured in the admin console and stored encrypted.
# Optional
FILE_STORAGE_PATH=data/files
WORKSPACE_DIR=data/workspace
AGENTS_DIR=../.claude/agents
```

Generating secrets:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Frontend (`.env`)

The frontend proxies `/api` requests through Vite (dev) or Nginx (production) — no extra configuration needed.

## 🐳 Docker commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f

# Enter containers
docker compose exec backend bash
docker compose exec postgres psql -U postgres -d agent_teams

# Back up the database
docker compose exec postgres pg_dump -U postgres agent_teams > backup.sql

# Restore the database
cat backup.sql | docker compose exec -T postgres psql -U postgres agent_teams
```

## 📚 Documentation

- [Quick start guide](./QUICKSTART.md) - Local development and Docker deployment (Chinese)
- [Docker deployment guide](./DOCKER.md) - Detailed Docker configuration (Chinese)
- [Medical AI disclaimer](./DISCLAIMER.md) - Scope of use and risk notice (Chinese)

## 🤝 Contributing

1. Fork the project
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'feat: add some feature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Commit conventions
- `feat:` new features
- `fix:` bug fixes
- `docs:` documentation
- `style:` code formatting
- `refactor:` refactoring
- `test:` tests
- `chore:` build/tooling

## 📄 License

This project is open source under the [AGPL-3.0](./LICENSE) license. The bundled [OpenHarness](./OpenHarness/) framework is MIT licensed.

## ⚕️ Medical disclaimer

The built-in medical-domain agents are intended solely for **organizing and assisting understanding of health information**. Their output does not constitute medical diagnosis, treatment advice, or prescriptions, and is not intended for use as a medical device. All clinical decisions must be made by licensed physicians. See [DISCLAIMER.md](./DISCLAIMER.md) (Chinese).

## 👥 Contact

- GitHub: [@nickzhang1102](https://github.com/nickzhang1102)

---

## ☕ Support the project

If Agent Teams helps you, consider buying the author a coffee ☕

**Every bit of support keeps this project maintained — it truly matters!**

| 💚 WeChat | 💙 Alipay |
| :---: | :---: |
| ![WeChat QR](website/sponsor/wechat.jpg) | ![Alipay QR](website/sponsor/alipay.jpg) |

A ⭐ Star is also greatly appreciated — it helps more people discover this project.
