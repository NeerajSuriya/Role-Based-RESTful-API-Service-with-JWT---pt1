# Role-Based Resource Management API

A small college project for managing shared resources. Users authenticate with JWTs, role checks protect staff actions, and PostgreSQL stores resources and request-to-return transaction history.

## Tech stack

- Python 3.11+
- FastAPI and Pydantic
- PostgreSQL, SQLAlchemy 2, and Alembic
- Argon2 password hashing (`pwdlib`) and JWT access tokens (`PyJWT`)
- `uv` and `pytest`

## Setup

Install PostgreSQL and [`uv`](https://docs.astral.sh/uv/), then create separate development and test databases. For example, with a local PostgreSQL account that has permission to create databases:

```bash
createdb resource_management
createdb resource_management_test
```

Install the project and configure the environment:

```bash
uv sync
cp .env.example .env
```

Edit `.env` with your PostgreSQL username/password and a random `JWT_SECRET_KEY` of at least 32 characters. `TEST_DATABASE_URL` must point to a separate PostgreSQL database whose name contains `test`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `APP_NAME` | FastAPI title | `Role-Based Resource Management API` |
| `DATABASE_URL` | Development/application PostgreSQL URL | `postgresql+psycopg://localhost/resource_management` |
| `TEST_DATABASE_URL` | Isolated PostgreSQL test URL | Unset; required to run integration tests |
| `JWT_SECRET_KEY` | Signs access tokens; keep it private | Unset; required for login tokens |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime | `30` |

Example URL format: `postgresql+psycopg://username:password@localhost:5432/resource_management`.

## Database migrations

Apply all pending migrations to the database in `DATABASE_URL`:

```bash
uv run alembic upgrade head
```

Check the current revision or migration history:

```bash
uv run alembic current
uv run alembic history
```

To roll back one migration (only when appropriate for your local development database):

```bash
uv run alembic downgrade -1
```

The integration-test fixture upgrades the separate `TEST_DATABASE_URL` database automatically. It rolls back test data and does not drop/reset that database.

## Run the API and Swagger UI

```bash
uv run uvicorn app.main:app --reload
```

- API base URL: <http://127.0.0.1:8000>
- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>
- Health check: `GET /health` (public)

In Swagger UI, use **Authorize** and enter the access token returned by login. The API uses HTTP Bearer authentication, which is included in the OpenAPI schema.

## Authentication, roles, and permissions

Register with `POST /auth/register` using an email and a password of at least eight characters. Public registration always creates a `student`; a client cannot assign itself a staff role. Log in with `POST /auth/login` to receive a short-lived JWT. Send it on protected requests as `Authorization: Bearer <access_token>`. Passwords are stored as Argon2 hashes.

| Role | Permissions |
| --- | --- |
| Student | View resources; read their own profile; request resources and view only their own transactions |
| Teacher | View resources; create/update/delete resources; manage transactions; read their own profile |
| Administrator | Teacher permissions; read any user profile |

A trusted operator must provision teacher/administrator accounts outside the public registration flow. For a local demo, register the account first, then have a trusted database operator promote it, for example:

```sql
UPDATE users SET role = 'teacher' WHERE email = 'teacher@example.com';
```

Do not expose database credentials or permit untrusted users to run role-changing SQL. Requests that violate role or ownership rules return `403 Forbidden`.

## Main endpoints

| Method and path | Access | Purpose |
| --- | --- | --- |
| `POST /auth/register` | Public | Register a student account |
| `POST /auth/login` | Public | Verify credentials and return a JWT |
| `GET /users/{user_id}` | Authenticated | Read own profile; administrator may read any profile |
| `GET /resources` | Authenticated | List resources; supports `search`, `category`, and `is_available` filters |
| `GET /resources/{resource_id}` | Authenticated | Read one resource |
| `POST /resources` | Teacher/administrator | Create a resource |
| `PATCH /resources/{resource_id}` | Teacher/administrator | Update a resource |
| `DELETE /resources/{resource_id}` | Teacher/administrator | Delete a resource without transaction history |
| `POST /transactions` | Authenticated | Create a pending request; students may request only for themselves |
| `GET /transactions` | Authenticated | List transactions; students see only their own |
| `GET /transactions/{transaction_id}` | Authenticated | Read a transaction; students may read only their own |
| `POST /transactions/{id}/approve` | Teacher/administrator | Approve a pending request and reserve stock |
| `POST /transactions/{id}/reject` | Teacher/administrator | Reject a pending request |
| `POST /transactions/{id}/borrow` | Teacher/administrator | Mark an approved request as borrowed |
| `POST /transactions/{id}/return` | Teacher/administrator | Mark a borrowed request as returned and restore stock |

Resource listing filters can be combined. `search` is a case-insensitive substring match on name/description; `category` is an exact match; `is_available` accepts `true` or `false`.

### Transaction lifecycle

`pending → approved → borrowed → returned`, or `pending → rejected`. Approval reserves the requested quantity atomically and updates resource availability; if stock is no longer available, the API returns `409 Conflict`. Borrowing records `borrowed_at`; returning restores the quantity, makes the resource available, and records `returned_at`. Invalid state changes also return `409 Conflict`.

## Demo flow

Start the API and set the base URL in a second terminal:

```bash
BASE_URL=http://127.0.0.1:8000
```

First, log in with an already provisioned teacher/administrator account and copy its `access_token` into `STAFF_TOKEN`. Use it to create an available resource; copy the returned `id` into `RESOURCE_ID`:

```bash
curl -sS -X POST "$BASE_URL/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"teacher@example.com","password":"your-password"}'

STAFF_TOKEN='<staff access_token>'

curl -sS -X POST "$BASE_URL/resources" \
  -H "Authorization: Bearer $STAFF_TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Demo Laptop","quantity":2,"is_available":true}'

RESOURCE_ID='<resource id>'
```

Register and log in as a student, then copy the returned account `id` and `access_token` into the variables below:

```bash
curl -sS -X POST "$BASE_URL/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"email":"student@example.com","password":"student-password"}'

curl -sS -X POST "$BASE_URL/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"student@example.com","password":"student-password"}'

STUDENT_ID='<student id>'
STUDENT_TOKEN='<student access_token>'

curl -sS "$BASE_URL/resources" \
  -H "Authorization: Bearer $STUDENT_TOKEN"

curl -sS -X POST "$BASE_URL/transactions" \
  -H "Authorization: Bearer $STUDENT_TOKEN" -H 'Content-Type: application/json' \
  -d "{\"user_id\":$STUDENT_ID,\"resource_id\":$RESOURCE_ID,\"quantity\":1}"

TRANSACTION_ID='<transaction id returned above>'
curl -sS -X POST "$BASE_URL/transactions/$TRANSACTION_ID/approve" -H "Authorization: Bearer $STAFF_TOKEN"
curl -sS -X POST "$BASE_URL/transactions/$TRANSACTION_ID/borrow" -H "Authorization: Bearer $STAFF_TOKEN"
curl -sS -X POST "$BASE_URL/transactions/$TRANSACTION_ID/return" -H "Authorization: Bearer $STAFF_TOKEN"
```

## Tests

Configure `TEST_DATABASE_URL` in `.env` to a dedicated PostgreSQL test database, then run:

```bash
uv run pytest -q
```

Tests cover authentication, token expiry, role/ownership permissions, resource CRUD/search, transaction state and inventory changes, validation failures, and the database schema. The test database name must contain `test` and must differ from `DATABASE_URL`.
