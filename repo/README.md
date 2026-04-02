# Practicum Assessment & Access Governance System

Practicum Assessment & Access Governance System is an offline-first internship assessment platform for universities and training institutions. It provides secure local authentication, role-based access governance, assessment authoring and delivery, grading workflows, reporting, audit logging, and encryption/masking of sensitive student identifiers without any cloud dependency.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 + Flask |
| Frontend | HTMX + Jinja2 templates |
| UI Framework | Bootstrap 5 |
| Database | SQLite 3 |
| Auth | Flask-Session + bcrypt |
| MFA | pyotp (offline TOTP) |
| Encryption | cryptography (Fernet) |
| Containerization | Docker Compose |

## Quick Start

1. Build and start the app:

```bash
docker compose up --build
```

2. Open the web app:
   - `http://localhost:5000`

3. Health check:

```bash
curl http://localhost:5000/health
```

## Demo Credentials

| Role | Username | Password |
|---|---|---|
| Department Admin | admin | Admin@Practicum1 |
| Faculty Advisor | advisor1 | Advisor@Practicum1 |
| Corporate Mentor | mentor1 | Mentor@Practicum1 |
| Student | student1 | Student@Practicum1 |

### Reset demo accounts

If demo credentials stop working (the bundled database is mutable), run:

> Note: A `.env` file with `DATABASE_URL` and `SECRET_KEY` must exist
> in the repo root before running seed or development commands locally.
> Copy `.env.example` to `.env` and adjust if needed.

```bash
# Docker
docker compose exec web python -c "from app import create_app; from app.seed import seed_db; app=create_app(); ctx=app.app_context(); ctx.push(); seed_db(); print('Done')"

# Local (without Docker)
FLASK_APP=app python -c "from app import create_app; from app.seed import seed_db; app=create_app('development'); ctx=app.app_context(); ctx.push(); seed_db(); print('Done')"
```

This resets all demo users to their documented passwords without deleting any data.

## Service URLs

- Web App: `http://localhost:5000`
- Health Check: `http://localhost:5000/health`

## Running Tests

```bash
bash run_tests.sh
```

`bash run_tests.sh` — runs all tests locally (no Docker required). Requires the `.venv` to be activated or dependencies installed.

## Local Development (Without Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate          # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
export FLASK_APP=app
export SECRET_KEY=dev-secret-key-change-me
flask run
```

Run tests locally:

```bash
python -m pytest tests/unit/ -q
python -m pytest tests/api/ -q
```

## Reset Database

Delete `data/practicum.db` and restart the container:

```bash
rm data/practicum.db
docker compose up --build
```

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `FLASK_APP` | Flask app module | `app` |
| `FLASK_ENV` | Flask environment | `development` |
| `SECRET_KEY` | Flask session secret key | `change-me...` |
| `DATABASE_URL` | SQLAlchemy DB URL | `sqlite:///data/practicum.db` |
| `FERNET_KEY` | Optional Fernet key (if empty, generated to `data/fernet.key`) | `<base64-key>` |
| `SESSION_TYPE` | Session backend | `filesystem` |
| `SESSION_LIFETIME_MINUTES` | Session timeout | `30` |
| `AUDIT_RETENTION_DAYS` | Audit log retention in days (default 3 years) | `1095` |

## Production Deployment

Before deploying to production:

1. Set `SECRET_KEY` to a cryptographically random string of at least 32 characters:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. Set `FLASK_ENV=production` (never run with `development` in production)
3. Generate and securely store a `FERNET_KEY` (or let the app auto-generate to `data/fernet.key` and back up that file)
4. Serve behind a reverse proxy (nginx/caddy) with HTTPS enabled
5. Restrict filesystem access to `data/` directory (contains database and encryption keys)
