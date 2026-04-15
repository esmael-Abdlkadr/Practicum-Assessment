# Practicum Assessment & Access Governance System

**Type:** Full-stack web application (Python/Flask backend + HTMX/Jinja2 frontend)

Offline-first internship assessment platform for universities and training institutions. Provides secure local authentication, role-based access governance, assessment authoring and delivery, grading workflows, reporting, audit logging, and encryption/masking of sensitive student identifiers — no cloud dependency required.

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

## Quick Start (Docker — recommended)

No `.env` file required. The app auto-generates a secure key on first run.

```bash
docker compose up --build
```

## Access

- Web app: `http://localhost:5000`
- Health check: `curl http://localhost:5000/health`

## Demo Credentials

| Role | Username | Password |
|---|---|---|
| Department Admin | admin | Admin@Practicum1 |
| Faculty Advisor | advisor1 | Advisor@Practicum1 |
| Corporate Mentor | mentor1 | Mentor@Practicum1 |
| Student | student1 | Student@Practicum1 |

## Running Tests

### Docker (required)

```bash
bash run_tests_docker.sh
```

Builds the test image (with Playwright chromium) and runs unit + API + HTTP integration + E2E suites inside Docker.

## Resetting Demo Data

If demo credentials stop working (the bundled database is mutable), run:

```bash
docker compose exec web python -c "from app import create_app; from app.seed import seed_db; app=create_app(); ctx=app.app_context(); ctx.push(); seed_db(); print('Done')"
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
| `FERNET_KEY` | Optional Fernet key (auto-generated to `data/fernet.key` if empty) | `<base64-key>` |
| `SESSION_TYPE` | Session backend | `filesystem` |
| `SESSION_LIFETIME_MINUTES` | Session timeout | `30` |
| `AUDIT_RETENTION_DAYS` | Audit log retention in days (default 3 years) | `1095` |

## Production Deployment

1. Set `SECRET_KEY` to a cryptographically random string of at least 32 characters:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. Set `FLASK_ENV=production`
3. Generate and securely store a `FERNET_KEY` (or let the app auto-generate to `data/fernet.key` and back up that file)
4. Serve behind a reverse proxy (nginx/caddy) with HTTPS enabled
5. Restrict filesystem access to `data/` directory (contains database and encryption keys)
