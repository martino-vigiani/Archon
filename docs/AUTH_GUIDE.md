# Authentication Guide

> JWT authentication flow, token lifecycle, and role-based permissions for the Archon REST API.

---

## Overview

Archon uses **stateless JWT bearer tokens** for authentication. There are no cookies or server-side sessions. Two token types work together:

| Token | TTL | Purpose | Stored In |
|-------|-----|---------|-----------|
| **Access token** | 30 minutes | Authorizes API requests | `Authorization: Bearer <token>` header |
| **Refresh token** | 7 days | Obtains new access tokens | Request body to `/auth/refresh` |

Both tokens are signed with HS256 using a shared secret (`ARCHON_SECRET_KEY`).

---

## Quick Start

### 1. Register

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "s3cur3P@ss!",
    "name": "Alice Chen"
  }'
```

Save the `access_token` and `refresh_token` from the response.

### 2. Call Protected Endpoints

```bash
export TOKEN="eyJhbGciOiJIUzI1NiIs..."

curl -s http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

### 3. Refresh When Expired

```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJhbGciOiJIUzI1NiIs..."}'
```

---

## Token Lifecycle

```
  Register / Login
        │
        ▼
  ┌─────────────────┐
  │ Access Token     │──── 30 min TTL ──── expires
  │ (short-lived)    │                        │
  └────────┬────────┘                        │
           │                                  │
  ┌────────┴────────┐                        │
  │ Refresh Token   │◄───── /auth/refresh ───┘
  │ (long-lived)    │         rotates
  └────────┬────────┘
           │
      7 day TTL
           │
        expires ──── must re-login
```

### Step-by-Step Flow

1. **Login** -- `POST /auth/login` with email + password. Server returns both tokens.
2. **Use access token** -- Include `Authorization: Bearer <access_token>` in all API requests.
3. **Access token expires** -- Server returns `401 UNAUTHORIZED`.
4. **Refresh** -- `POST /auth/refresh` with the refresh token. Server revokes the old refresh token and issues a new pair (rotation).
5. **Refresh token expires** -- User must log in again with credentials.
6. **Logout** -- `DELETE /auth/logout` with access token. Revokes the session.

### Token Rotation

Every call to `/auth/refresh` **revokes the old refresh token** and issues a new one. This limits damage if a refresh token is stolen:

- The attacker gets one use.
- When the legitimate user refreshes the same token, it's already revoked -- signaling compromise.

### Token Payload

Access tokens contain:

```json
{
  "sub": "user-uuid",
  "role": "admin",
  "type": "access",
  "iss": "archon",
  "iat": 1708437600,
  "exp": 1708439400
}
```

Refresh tokens contain:

```json
{
  "sub": "user-uuid",
  "type": "refresh",
  "iss": "archon",
  "iat": 1708437600,
  "exp": 1709042400
}
```

No sensitive data is stored in the payload. The token is verifiable without a database lookup.

---

## Role-Based Access Control (RBAC)

### Role Hierarchy

```
ADMIN (level 2)  >  OPERATOR (level 1)  >  VIEWER (level 0)
```

Higher roles inherit all permissions of lower roles.

### Permissions by Role

| Action | VIEWER | OPERATOR | ADMIN |
|--------|--------|----------|-------|
| View dashboard | Yes | Yes | Yes |
| Read own profile (`GET /users/me`) | Yes | Yes | Yes |
| List resources (`GET /resources`) | Yes | Yes | Yes |
| Update own profile (`PUT /users/me`) | Yes | Yes | Yes |
| Trigger orchestrator actions | No | Yes | Yes |
| List all users (`GET /auth/users`) | No | No | Yes |
| Manage user accounts | No | No | Yes |

### First User Auto-Promotion

The **first user to register** is automatically promoted to `ADMIN`. All subsequent users are created as `VIEWER` by default. This bootstraps the admin without config files or manual database edits.

### Checking Roles in Code

The middleware provides two FastAPI dependencies:

```python
from orchestrator.auth.middleware import get_current_user, require_role
from orchestrator.auth.models import Role, User

# Any authenticated user
@app.get("/protected")
async def protected(user: User = Depends(get_current_user)):
    return {"user": user.username}

# Admin only
@app.delete("/admin-only")
async def admin_only(user: User = Depends(require_role(Role.ADMIN))):
    return {"message": "admin access granted"}

# Operator or higher
@app.post("/operator-action")
async def operator_action(user: User = Depends(require_role(Role.OPERATOR))):
    return {"message": "action performed"}
```

---

## Password Policy

| Rule | Value | Configurable |
|------|-------|--------------|
| Minimum length | 8 characters | `AuthConfig.min_password_length` |
| Maximum length | 128 characters | Pydantic field constraint |
| Hashing | bcrypt, 12 rounds | `PasswordHasher` in `auth/passwords.py` |
| Complexity | No requirements | By design for local dev tool |

Passwords are never stored in plaintext. The `PasswordHasher` uses `bcrypt.gensalt(rounds=12)` which provides ~2^12 iterations of the Blowfish cipher.

---

## Error Responses

All auth errors use the contract-compliant nested format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable explanation.",
    "details": null
  }
}
```

### Common Auth Errors

| HTTP | Code | Message | Cause |
|------|------|---------|-------|
| `401` | `UNAUTHORIZED` | "Authentication required" | No `Authorization` header |
| `401` | `UNAUTHORIZED` | "Token has expired" | Access token TTL exceeded |
| `401` | `INVALID_CREDENTIALS` | "Email or password is incorrect." | Wrong login credentials |
| `401` | `INVALID_TOKEN` | "Token has been revoked" | Refresh token already used |
| `403` | `FORBIDDEN` | "Account is deactivated" | `is_active = false` |
| `403` | `FORBIDDEN` | "Role 'viewer' insufficient..." | RBAC check failed |
| `409` | `CONFLICT` | "A user with this email already exists." | Duplicate registration |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ARCHON_SECRET_KEY` | Random (changes on restart) | JWT signing key. **Set explicitly for production.** |
| `ARCHON_ACCESS_TOKEN_MINUTES` | `30` | Access token TTL in minutes |
| `ARCHON_REFRESH_TOKEN_DAYS` | `7` | Refresh token TTL in days |
| `ARCHON_DB_PATH` | `.orchestra/auth.db` | SQLite database path |
| `ARCHON_MIN_PASSWORD_LENGTH` | `8` | Minimum password length |

### Generating a Secret Key

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Store in `.env` (never commit):

```bash
ARCHON_SECRET_KEY=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
```

### AuthConfig Dataclass

All settings live in `orchestrator/auth/config.py`:

```python
@dataclass
class AuthConfig:
    secret_key: str           # From ARCHON_SECRET_KEY or random
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    db_path: Path             # .orchestra/auth.db
    min_password_length: int = 8
    issuer: str = "archon"
```

---

## Database Schema

User data is stored in SQLite at `.orchestra/auth.db`:

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_users_username ON users (username);
CREATE INDEX idx_users_email ON users (email);
```

The resource database (`live_api.db`) stores protected resources:

```sql
CREATE TABLE resources (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

---

## Testing Authentication

### Full Lifecycle Test

```bash
# 1. Register
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "testpass123", "name": "Test User"}')

ACCESS=$(echo $RESPONSE | python -c "import sys,json; print(json.load(sys.stdin)['tokens']['access_token'])")
REFRESH=$(echo $RESPONSE | python -c "import sys,json; print(json.load(sys.stdin)['tokens']['refresh_token'])")

# 2. Use access token
curl -s http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer $ACCESS" | python -m json.tool

# 3. List resources
curl -s http://localhost:8000/api/v1/resources \
  -H "Authorization: Bearer $ACCESS" | python -m json.tool

# 4. Refresh tokens
NEW_TOKENS=$(curl -s -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH\"}")

echo $NEW_TOKENS | python -m json.tool

# 5. Old refresh token is now revoked (this should fail)
curl -s -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH\"}" | python -m json.tool

# 6. Logout
curl -s -X DELETE http://localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer $ACCESS" | python -m json.tool
```

### Running the Test Suite

```bash
# Unit tests for auth module
pytest tests/test_auth.py -v

# Integration tests (44 HTTP tests)
pytest tests/test_auth_integration.py -v

# Security tests (OWASP checks)
pytest tests/test_security.py -v

# All security-marked tests
pytest -m security -v
```

---

## Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| **JWT over sessions** | No shared session store needed. Dashboard (:8420) and API (:8000) are separate processes. |
| **HS256 over RS256** | Single-service architecture. No third-party token verification needed. Faster. |
| **Token rotation** | Limits stolen refresh token to one use. Creates detectable anomaly. |
| **SQLite** | Zero-config, single-file, Python stdlib. Sufficient for local/small-team usage. |
| **In-memory blacklist** | Acceptable for local dev tool. Server restart clears it. |

For production hardening details, see [Architecture & Security](./ARCHITECTURE_AND_SECURITY.md).

---

## See Also

- [API Reference](./API_REFERENCE.md) -- Full endpoint documentation with curl examples
- [Architecture & Security](./ARCHITECTURE_AND_SECURITY.md) -- Threat model, security posture, hardening
- [Deployment Guide](./DEPLOYMENT.md) -- Docker, production config, checklist
- [Getting Started](./GETTING_STARTED.md) -- First-run walkthrough
