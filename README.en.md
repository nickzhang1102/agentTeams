# 🤝 Agent Teams

**Stop chatting with a single bot — hand your complex problem to an auto-assembled team of AI experts**

Leader orchestration · DAG parallel execution · SSE streaming · 107 expert agents · Knowledge graph GraphRAG

[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](./LICENSE)
[![Status](https://img.shields.io/badge/status-early%20release-yellow.svg)](#-why-agent-teams)
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688.svg)](#-quick-start-docker)
[![Frontend](https://img.shields.io/badge/frontend-Vue%203-42b883.svg)](#-quick-start-docker)
[![Docker](https://img.shields.io/badge/deploy-Docker%20Compose-2496ED.svg?logo=docker&logoColor=white)](#-quick-start-docker)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-181717.svg?logo=github)](https://nickzhang1102.github.io/agentTeams/)

English | [简体中文](./README.md)

![Agent Teams home](website/screenshots/desktop-home.png)

[Project website](https://nickzhang1102.github.io/agentTeams/) · [Quick start](#-quick-start-docker) · [Screenshots](#-screenshots) · [Contributing](#-contributing) · [☕ Buy the author a coffee](#-support-the-project)

> **Status**: This project is public and in an early stage — trials and feedback are welcome. Before deploying to the public internet, complete the required items in the [Security](#-security) section.

---

## 🎯 Why Agent Teams

Most AI products give you a chat window; complex problems usually need a **team**. If you have ever tried to use AI for real work, these will sound familiar:

| Reality | Agent Teams' answer |
|---------|----------------|
| 🤖 A single chatbot has one point of view and loses the big picture on complex problems | Describe your problem and the **Leader auto-assembles an expert team** — 107 domain experts cross-checking from multiple angles |
| 🔁 Consulting several AIs one by one and copy-pasting context back and forth | The Leader orchestrates everything: requirement assessment → team formation → **tasks decomposed into a DAG executed in parallel** → one synthesized report |
| 🧰 Professional questions lack structured methodology, and prompts are improvised every time | 107 built-in experts across medicine, business roles, finance and futures — each carrying its own domain framework, ready out of the box |
| 🕳️ The AI gives a conclusion and stops — the process is a black box with no evidence trail | Subtask decomposition and **raw tool outputs are persisted end-to-end**, so reports drill down to the original evidence |
| ☁️ Sensitive material you would rather not hand to a third-party platform | **Fully self-hosted**: data stays in your own PostgreSQL; LLM and search credentials are configured inside the project and stored encrypted |

Agent Teams is built for individuals and small teams who want an "AI team", not an "AI chat window": self-deploy with one command, responsive on desktop and mobile, bilingual UI — AI does the organizing and analysis, and the final judgment always stays yours.

---

## ✨ Features

### 🤖 Multi-agent orchestration
| Feature | Description |
|------|------|
| 🧠 **Leader Agent** | Requirement assessment → team formation → task decomposition into a **DAG execution plan** → batched parallel execution → result synthesis, no manual intervention |
| 🔍 **Transparent & traceable** | Subtask decomposition and raw tool outputs are persisted; the final report drills down to original evidence |
| 🔄 **Dynamic subtasks** | Subtasks can be appended during execution, guarded by upper limits |
| 🧯 **Fault-tolerant execution** | A single tool failure does not abort the run — partial results still feed subsequent reasoning |

### 👥 Expert matrix
| Feature | Description |
|------|------|
| 👥 **107 built-in experts** | Medical specialties (internal/surgical/subspecialty/diagnostics), business roles (CEO·CTO·CFO·Product·UI·Interaction), finance & futures (CIO·CRO·Quant·macro/steel/nonferrous/agriculture analysts…), dynamically categorized and ready to use |
| 📦 **AgentPacks** | Bundle frequently used experts into packs — system presets work instantly, clones are editable |
| 📋 **Workflow templates** | Preconfigured teams and assessment thresholds, launched with one click |

> Note: some business/finance agents are named after public figures (e.g. "CEO (Bezos mental model)"). This is solely a tribute to and borrowing of their publicly shared methodologies and thinking styles — no affiliation, endorsement, or representation is implied. Medical agents are named after clinical departments; see the [medical disclaimer](#️-medical-disclaimer) for their intended scope.

### 💬 Chat experience
| Feature | Description |
|------|------|
| ⚡ **SSE streaming** | Typewriter-style real-time output with live per-agent execution status |
| 📄 **Rich text & export** | Markdown + code highlighting; export reports as PDF / image and share conversations |
| 🌗 **Dark mode & i18n** | One-click theme switching; Chinese / English interface; responsive mobile layout |
| 💡 **Suggested questions** | Follow-up directions recommended after each answer |

### 🧠 Knowledge & platform
| Feature | Description |
|------|------|
| 🕸️ **Knowledge graph** | D3 visualization, GraphRAG retrieval, gap analysis |
| 📎 **Document understanding** | PDF / DOCX / XLSX / PPTX parsing with OCR, file versioning |
| 🧩 **MCP tool ecosystem** | MCP tool registration and management, full tool-call audit logs |
| 🖥️ **Admin console** | Dashboard statistics, visual agent editing, performance monitoring, system settings |

---

## 📸 Screenshots

> All screenshots below were captured from the current frontend loaded with fixed fictional demo data. No real user information is included.

**Final report** — expert conclusions synthesized into a structured report that drills down to evidence

![Final report](website/screenshots/desktop-final-report.png)

**Orchestration view** — the Leader decomposes tasks into stages and subtasks; every agent's status is live

![Orchestration view](website/screenshots/desktop-conversation-detail.png)

### 📁 More screenshots (expert matrix / templates / admin / settings)

**Agent gallery** — 107 domain experts categorized by field

![Agent gallery](website/screenshots/desktop-agents.png)

**Team presets** — system AgentPacks and workflow templates, one click away

![Team presets](website/screenshots/desktop-templates.png)

**Admin console** — dashboard statistics, performance monitoring and system settings in one place

![Admin console](website/screenshots/desktop-admin.png)

**Project settings** — LLM and search credentials configured in-project, stored encrypted

![Project settings](website/screenshots/desktop-project-settings.png)

**Mobile**

| ![Mobile home](website/screenshots/mobile-home.png) | ![Mobile orchestration](website/screenshots/mobile-conversation.png) | ![Mobile agents](website/screenshots/mobile-agents.png) | ![Mobile templates](website/screenshots/mobile-templates.png) |
|---|---|---|---|

---

## 🚀 Quick Start (Docker)

The fastest way is to bring up the full stack with Docker Compose.

### 1️⃣ Clone & configure

```bash
git clone https://github.com/nickzhang1102/agentTeams.git
cd agentTeams
cp backend/.env.example backend/.env
```

Edit `backend/.env` — the following 2 variables are **required** (the deploy script enforces strength):

| Variable | Description | How to generate |
|------|------|----------|
| `SECRET_KEY` | Application root secret (≥32 chars), also encrypts database credentials | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `JWT_SECRET_KEY` | JWT signing secret (≥32 chars) | Same as above |

> **No LLM configuration needed upfront**: after deployment, sign in and add any OpenAI-compatible model under "LLM Models" in the admin console; Exa/Tavily keys go under "System Settings". All credentials are stored encrypted.

### 2️⃣ Deploy

```bash
# Linux / macOS
./scripts/docker-deploy.sh

# Windows (PowerShell)
.\scripts\docker-deploy.ps1
```

The script builds images → starts services → runs database migrations (idempotent). The frontend is exposed on port `8380`; PostgreSQL and the backend bind only to the host loopback interface. See [DOCKER.md](./DOCKER.md) (Chinese) for details.

### 3️⃣ Access

- Frontend: <http://localhost:8380>
- Admin account `admin`. **Recommended**: set `ADMIN_INITIAL_PASSWORD` in `backend/.env` before starting (at least 8 characters, letters and digits required) — on first creation it becomes the admin initial password directly, no log digging needed. If unset, a random password is generated: check the most recent "admin created" line in `docker compose logs backend` (logs persist across container recreations — stale lines show dead passwords), or the host file `backend/data/.admin_initial_password` (`admin/admin123` only applies to local development with `APP_ENV=development`). Forgot the password or locked out: `docker compose exec -e ADMIN_INITIAL_PASSWORD='NewPass' backend python reset_admin.py`.

---

## 💻 Local development

Prerequisites: Node.js 20.19+ · Python 3.11+ · PostgreSQL 18 · an OpenAI-compatible LLM service account

```bash
# Backend (http://localhost:5000)
cd backend
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -e ../OpenHarness                        # bundled execution framework, required for local dev
cp .env.example .env                                 # set DATABASE_URL / SECRET_KEY / JWT_SECRET_KEY
alembic upgrade head                                 # initialize the database
python init_admin.py                                 # create admin (admin/admin123 under development)
python run.py

# Frontend (http://localhost:5173, new terminal)
cd frontend
npm install
npm run dev
```

Full steps and troubleshooting: [QUICKSTART.md](./QUICKSTART.md) (Chinese).

---

## 🔒 Security

- **Auth & transport**: JWT + httpOnly Cookie (SameSite=Strict); passwords hashed with pbkdf2 + RSA-encrypted transmission
- **Secret governance**: `SECRET_KEY` / `JWT_SECRET_KEY` are validated at startup — boot refuses to proceed when missing or too weak (fail-closed); database credentials are encrypted with the root secret, rotation documented in `.env.example`
- **Upload protection**: uploads are validated via streaming chunk checks to prevent memory exhaustion from oversized files
- **Production posture by default**: everything starts in production mode unless `APP_ENV=development` is explicitly set

Required changes for public deployments: strong random secrets, changed default admin password, HTTPS terminated by a reverse proxy with only ports 80/443 open, regular database backups. See [DOCKER.md](./DOCKER.md) and [SECURITY.md](./SECURITY.md) (Chinese).

---

## ⚠️ Medical disclaimer

The built-in medical-domain agents are intended solely for **organizing and assisting understanding of health information**. Their output does not constitute medical diagnosis, treatment advice, or prescriptions, and is not intended for use as a medical device. All clinical decisions must be made by licensed physicians. See [DISCLAIMER.md](./DISCLAIMER.md) (Chinese).

---

## 📄 License

This project is available under a **dual-license** model:

- **Open source**: licensed under [AGPL-3.0](./LICENSE). Offering this software to others as a network service (SaaS) also triggers the AGPL-3.0 source-sharing obligation.
- **Commercial license**: organizations that cannot comply with AGPL-3.0 (closed-source commercial use, private SaaS deployments, etc.) may contact the maintainer for a commercial license. nickzhang1102@163.com
- The bundled [OpenHarness](./OpenHarness/) framework is MIT licensed. External contributions require signing a CLA to sustain the dual-license model — see [CONTRIBUTING.md](./CONTRIBUTING.md).

Copyright © 2026 nickzhang1102 · GitHub [@nickzhang1102](https://github.com/nickzhang1102)

---

## 🤝 Contributing

Contributions are welcome! Fork → create a feature branch → commit (Conventional Commits: `feat:` / `fix:` / `docs:` etc.) → open a Pull Request. See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full workflow.

---

## ☕ Support the project

If Agent Teams helps you, consider buying the author a coffee ☕

**Every bit of support keeps this project maintained — it truly matters!**

| 💚 WeChat | 💙 Alipay |
| :---: | :---: |
| ![WeChat QR](website/screenshots/wechat.jpg) | ![Alipay QR](website/screenshots/alipay.jpg) |

A ⭐ Star is also greatly appreciated — it helps more people discover this project.
