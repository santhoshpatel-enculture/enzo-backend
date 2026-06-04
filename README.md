# Enzo Backend

Premium AI Assistant backend for the Enculture platform.

## Tech Stack
- **Framework:** Python FastAPI
- **Database:** MongoDB (async via Motor)
- **Auth:** JWT (python-jose) + bcrypt password hashing (direct `bcrypt` library)
- **AI:** Groq (Llama 3 8B) with streaming support
- **Validation:** Pydantic v2

## Quick Start

### 1. Prerequisites
- Python 3.12+
- MongoDB running on `127.0.0.1:27017`

### 2. Setup
```bash
cp .env.example .env
# Edit .env — set GROQ_API_KEY and optionally JWT_SECRET_KEY

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run
```bash
uvicorn app.main:app --reload --port 8000
```

### 4. API Docs
Open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive Swagger UI.

## Deploy on Vercel

Use a **separate** Vercel project linked to the `enzo-backend` repo. Set **Root Directory** to `.` (repo root). Vercel auto-detects FastAPI via `app/main.py` and `pyproject.toml` (`tool.vercel.entrypoint`). Do **not** add a legacy `api/` serverless folder or `functions` patterns in `vercel.json`.

See [../DEPLOYMENT.md](../DEPLOYMENT.md) for env vars, CORS, and security checklist.

## Demo Credentials

Default bootstrap password for employee accounts: **Test@1234** (users should change it on first login).

Run `python scratch/set_default_passwords.py --email you@enculture.ai` to set or reset a user's password and flag `mustChangePassword`.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/auth/login | Login with email + password (sets refresh cookie) |
| POST | /api/auth/refresh | Rotate refresh cookie → new access token |
| GET | /api/auth/sso/microsoft/start | Microsoft Entra SSO redirect |
| GET | /api/auth/sso/microsoft/callback | SSO callback |
| POST | /api/auth/change-password | Change password (authenticated) |
| POST | /api/auth/logout | Logout (revoke refresh cookie) |
| GET | /api/auth/me | Current user profile |
| POST | /api/chat/feedback | Thumbs up/down on assistant message |
| GET | /api/org/manager | Reporting manager |
| GET | /api/org/reportees | Direct reports |
| GET | /api/org/tree | Reporting-line org tree (managers above + reportees below) |
| GET | /api/programs | Program participation list (metadata only) |
| GET | /api/programs/:id | Program detail (no answers) |
| GET | /api/profile | User profile details |
| GET | /api/tasks | List tasks (with filters) |
| GET | /api/tasks/pending | Pending tasks |
| GET | /api/tasks/critical | Critical/high priority tasks |
| GET | /api/tasks/upcoming | Tasks due within N days |
| POST | /api/chat/message | Send chat message (streaming SSE) |
| GET | /api/chat/history | List conversations |
| GET | /api/chat/history/:id | Load conversation |
| DELETE | /api/chat/history/:id | Delete conversation |
| DELETE | /api/chat/history | Clear all history |
| GET | /api/dashboard/summary | Dashboard metrics + insights |
| GET | /api/settings | Get user settings |
| PUT | /api/settings | Update user settings |

### Admin API (RBAC: `adminRole` on user, or `ADMIN_EMAILS` bootstrap)

Send `X-Admin-Tenant-Id` header for super_admin tenant scope.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/admin/metrics | Platform analytics |
| GET | /api/admin/users | List users (with filter options; team, gender, age, manager) |
| POST | /api/admin/users | Create user |
| PATCH | /api/admin/users/:id | Update user / role |
| DELETE | /api/admin/users/:id | Soft-delete user |
| GET | /api/admin/config | Groq / prompt platform config |
| PUT | /api/admin/config | Update platform config |
| GET | /api/admin/kb | List knowledge base documents |
| POST | /api/admin/kb/upload | Upload and index document |
| DELETE | /api/admin/kb/:id | Remove document |
| GET | /api/admin/conversations | Audit conversation list |
| GET | /api/admin/conversations/:id | Full conversation |
| DELETE | /api/admin/conversations/:id | Delete conversation |
| GET | /api/admin/tasks | Cross-user task list |
| GET | /api/admin/telemetry/summary | Usage telemetry (messages, tokens, cost by tenant/user) |
| GET | /api/admin/telemetry/users | Per-user usage breakdown |
| PUT | /api/admin/telemetry/pricing | Update token cost rates (USD per 1M) |
| GET | /api/admin/tenants/:id/budget | Tenant monthly budget + usage |
| PUT | /api/admin/tenants/:id/budget | Update tenant budget limits |
| GET | /api/admin/feedback/summary | Message feedback counts |

Chat conversations are persisted in MongoDB (`conversations` collection).

### Prompt files (editable in Admin Console)

| File | Admin tab | Description |
|------|-----------|-------------|
| `prompts/system_prompt.md` | Chatbot | Custom system instructions for Enzo |
| `prompts/knowledge_base.md` | Knowledge Base | Default markdown knowledge (uploads are merged at runtime) |

Saving from the dashboard writes these files and syncs MongoDB `platform_config`.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| MONGO_URI | No | mongodb://127.0.0.1:27017 | MongoDB connection string |
| MONGO_DB_NAME | No | enzo_db | Database name |
| JWT_SECRET_KEY | Yes (prod) | Auto-generated (dev) | JWT signing secret |
| GROQ_API_KEY | Yes | — | Groq API key for LLM |
| GROQ_MODEL | No | llama3-8b-8192 | Default Groq model (legacy; primary set in admin) |
| OPENAI_API_KEY | No | — | OpenAI key for fallback (e.g. gpt-4o-mini) |
| CORS_ORIGINS | No | localhost/127.0.0.1 on 5173–5175 | Comma-separated allowed origins |
| ADMIN_EMAILS | No | admin@enculture.ai,santhosh@enculture.ai | Emails allowed to use Enzo-admin |
| ADMIN_UPLOAD_DIR | No | uploads/kb | KB file storage path |
| ADMIN_MAX_UPLOAD_MB | No | 10 | Max upload size per file |
