# COMP 3613 Job Board (Phase 2 starter)

Flawed baseline **0.2.0** built on [uwidcit/faststart](https://github.com/uwidcit/faststart) (`96ccfce`).

FastStart provides the SSR shell, JWT cookie auth, SQLModel, `manage.py`, and Render/Docker wiring. The job-board scenario adds domain models/services and a JSON API under `/api` (see `/docs`).

## Quick start

```text
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Windows: Copy-Item .env.example .env
python manage.py init
python manage.py run
```

Open http://127.0.0.1:5000 — SSR auth shell; scenario JSON under `/api` and OpenAPI at `/docs`.

## Seeded API accounts

| Email | Password | Role |
| --- | --- | --- |
| `admin@example.com` | `admin-dev` | admin |
| `grad.dcit@example.com` | `grad-dev` | graduate (DCIT) |
| `grad.other@example.com` | `grad-dev` | graduate (OTHER) |
| `employer@example.com` | `employer-dev` | employer |
| `employer2@example.com` | `employer-dev` | employer |

JSON login: `POST /api/auth/login` with `{"email","password"}`.

## Student brief

See [`ASSIGNMENT.md`](ASSIGNMENT.md) and [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md).

## Tests

```bash
python -m pytest tests -q
```

## API authentication and authorization

Protected job-board API routes derive the acting user from the signed
`access_token` cookie issued by `/login` or `/api/auth/login`. Do not send an
`actor_id` to choose an identity; authorization uses the authenticated user,
and employers can access applicant data or change application status only for
their own listings. Administrators may review listings and access authorized
applicant export functions, but cannot transition application statuses.

Successful application status changes are written atomically to
`ApplicationStatusHistory`, including the previous status, new status, actor,
and UTC timestamp. Failed or unchanged transitions do not create history.
