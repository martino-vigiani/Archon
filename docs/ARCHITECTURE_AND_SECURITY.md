# Architecture & Security Guide

Archon REST API authentication system: architectural decisions, security posture, and deployment guidance.

---

## Architectural Decisions

### Why JWT Over Server-Side Sessions

**Decision:** Stateless JWT bearer tokens, not cookie-based sessions.

**Rationale:**
- Archon is a local-first dev tool, not a multi-server web app. JWTs eliminate the need for a shared session store (Redis, Memcached) that would add operational complexity for zero benefit.
- The dashboard (`localhost:8420`) and live API (`localhost:8000`) are separate FastAPI processes. JWTs work across both without shared state.
- Stateless verification means no database lookup on every request — just decode and validate the signature. For a dev tool that may process many API calls in burst, this matters.
- Future multi-terminal verification: any terminal can validate a JWT independently using the shared secret, without calling back to a central session store.

**Trade-offs accepted:**
- Tokens cannot be instantly revoked server-side (mitigated by short access token TTL and refresh token blacklist).
- Token payload is readable by the client (we only include `sub`, `role`, `type` — no sensitive data).

### Why HS256, Not RS256

**Decision:** HMAC-SHA256 symmetric signing, not RSA asymmetric.

**Rationale:**
- Single-service architecture. There is no third-party that needs to verify tokens without the signing key. RS256's public/private key separation adds complexity with no benefit here.
- HS256 is faster for both signing and verification — relevant for a local dev tool.
- Simpler key management: one `ARCHON_SECRET_KEY` env var vs. PEM file management, key rotation ceremonies, and JWKS endpoints.

**When to reconsider:** If Archon ever exposes a public API consumed by third-party plugins that need to verify tokens without accessing the signing key, migrate to RS256 with a JWKS endpoint.

### Token Rotation Strategy

**How it works:**
1. User logs in → receives access token (30 min) + refresh token (7 days).
2. Access token expires → client calls `POST /auth/refresh` with the refresh token.
3. Server revokes the old refresh token and issues a new pair.
4. On logout, the refresh token is revoked.

**Why rotate refresh tokens:**
- Limits the damage window if a refresh token is stolen. The attacker gets one use — as soon as the legitimate user refreshes, the stolen token is invalid.
- Creates a detectable anomaly: if both the attacker and user try to refresh the same token, one will fail, signaling compromise.

**Current limitation:** The revocation blacklist is in-memory (`TokenService._revoked_tokens: set[str]`). Server restarts clear it. This is acceptable for a local dev tool but must be addressed for any networked deployment (see [Hardening for Production](#hardening-for-production)).

### Password Policy

**Current policy** (enforced in `auth/config.py` and `auth/models.py`):
- Minimum 8 characters (configurable via `AuthConfig.min_password_length`)
- Maximum 128 characters (Pydantic field constraint)
- No complexity requirements (uppercase, special chars, etc.)

**Rationale:** For a local dev tool, password complexity rules add friction without proportional security gain. The primary threat model is unauthorized access to the dashboard, not brute-force attacks from the internet.

**Recommended enhancements for networked deployments:**
- Add `zxcvbn`-style strength estimation (rejects common passwords like `password123`)
- Enforce minimum entropy rather than character class rules
- Consider passphrase support (minimum 16 chars with no complexity requirement as alternative)

### Role-Based Access Control

**Three-tier hierarchy** (defined in `auth/models.py:Role`):

```
ADMIN (2) > OPERATOR (1) > VIEWER (0)
```

| Role | Can Do | Use Case |
|------|--------|----------|
| VIEWER | Read dashboard, view status | Observers, stakeholders |
| OPERATOR | All viewer perms + trigger actions | Developers using Archon |
| ADMIN | All operator perms + manage users | System administrators |

**Design decisions:**
- First registered user auto-promotes to ADMIN (bootstrapping without config files).
- Permission check is hierarchical: `ADMIN` implicitly has all `OPERATOR` and `VIEWER` permissions.
- Roles are stored as strings in SQLite, not integers — human-readable and extensible.

### Database Choice: SQLite

**Why SQLite, not PostgreSQL/MySQL:**
- Zero-config: no database server to install, configure, or manage.
- Single-file storage at `.orchestra/auth.db` — lives alongside project state.
- Sufficient for single-user/small-team local usage (thousands of users, not millions).
- Python's `sqlite3` is in the standard library — no additional dependencies.

**Indexes** (defined in `auth/database.py`):
- `idx_users_username` — fast login lookup
- `idx_users_email` — fast email uniqueness check

---

## Security Posture

### Current State (v1.0)

What's implemented and what's missing:

| Control | Status | Location |
|---------|--------|----------|
| Password hashing (bcrypt, 12 rounds) | Implemented | `auth/passwords.py` |
| JWT access tokens (30 min TTL) | Implemented | `auth/tokens.py` |
| JWT refresh tokens (7 day TTL) | Implemented | `auth/tokens.py` |
| Refresh token rotation | Implemented | `auth/routes.py:refresh` |
| Refresh token revocation | Implemented (in-memory) | `auth/tokens.py` |
| Role-based access control | Implemented | `auth/middleware.py` |
| Input validation (Pydantic) | Implemented | `auth/models.py` |
| Consistent error format | Implemented | `auth/error_handlers.py` |
| SQL injection prevention | Implemented (parameterized queries) | `auth/database.py` |
| Rate limiting | **Not implemented** | — |
| CORS restriction | **Not implemented** (allow all) | `live_api.py:382` |
| HTTPS enforcement | **Not implemented** | — |
| CSRF protection | **Not needed** (no cookies) | — |
| Audit logging | **Not implemented** | — |
| Account lockout | **Not implemented** | — |

### Threat Model

Archon's primary deployment: a developer's local machine or private network.

| Threat | Likelihood | Impact | Mitigation |
|--------|-----------|--------|------------|
| Brute-force login | Low (local) | Medium | Rate limiting (recommended) |
| Token theft via XSS | Low (admin UI is local) | High | HttpOnly storage, CSP headers |
| Token theft via network sniffing | Medium (if not HTTPS) | High | HTTPS enforcement |
| SQL injection | Very Low | Critical | Parameterized queries (implemented) |
| Privilege escalation | Low | High | RBAC hierarchy check (implemented) |
| Refresh token reuse after rotation | Low | Medium | Revocation blacklist (implemented) |
| Server restart clears blacklist | Medium | Low | Persistent blacklist (recommended) |

---

## Security Recommendations

### 1. Rate Limiting

**Priority: High** — prevents brute-force attacks on login and registration.

**Recommended approach:** Use `slowapi` (built on `limits`), which integrates with FastAPI.

```python
# In live_api.py or a dedicated middleware module
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Auth endpoints: strict limits
@auth_router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, data: LoginRequest, ...):
    ...

@auth_router.post("/register")
@limiter.limit("3/minute")
async def register(request: Request, data: RegisterRequest, ...):
    ...

@auth_router.post("/refresh")
@limiter.limit("10/minute")
async def refresh(request: Request, data: RefreshRequest, ...):
    ...

# Protected endpoints: generous limits
@resources_router.get("")
@limiter.limit("60/minute")
async def list_resources(request: Request, ...):
    ...
```

**Recommended limits:**
| Endpoint | Limit | Rationale |
|----------|-------|-----------|
| `POST /auth/login` | 5/min per IP | Brute-force prevention |
| `POST /auth/register` | 3/min per IP | Abuse prevention |
| `POST /auth/refresh` | 10/min per IP | Normal usage allows frequent refresh |
| All other endpoints | 60/min per IP | General abuse prevention |

**Dependency:** `pip install slowapi`

### 2. CORS Configuration

**Priority: High** — current config at `live_api.py:382` allows all origins.

**Current (insecure):**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # Anyone can call the API
    allow_credentials=True,        # Combined with *, this is dangerous
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Recommended:**
```python
ALLOWED_ORIGINS = os.environ.get(
    "ARCHON_CORS_ORIGINS",
    "http://localhost:8420,http://localhost:8000,http://127.0.0.1:8420,http://127.0.0.1:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

**Why this matters:** `allow_origins=["*"]` with `allow_credentials=True` means any website the developer visits could make authenticated requests to their local Archon API.

### 3. HTTPS Enforcement

**Priority: Medium** — critical for any non-localhost deployment.

For local development, HTTP on `localhost` is acceptable. For any networked deployment:

```python
# Option A: Reverse proxy (recommended)
# Use nginx, Caddy, or Cloudflare Tunnel in front of Archon.
# Caddy auto-provisions TLS certificates.

# Option B: Direct TLS in uvicorn
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8000,
    ssl_keyfile="/path/to/key.pem",
    ssl_certfile="/path/to/cert.pem",
)

# Option C: HSTS header middleware (add after TLS is configured)
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

if os.environ.get("ARCHON_REQUIRE_HTTPS") == "true":
    app.add_middleware(HTTPSRedirectMiddleware)
```

### 4. Token Storage Best Practices (Client-Side)

**For the admin dashboard (`admin.html`):**

| Storage Method | XSS Risk | CSRF Risk | Recommendation |
|---------------|----------|-----------|----------------|
| `localStorage` | High (accessible via JS) | None | Avoid for access tokens |
| `sessionStorage` | Medium (same-tab only) | None | Acceptable for short sessions |
| In-memory (JS variable) | Low (not persisted) | None | **Best for access tokens** |
| HttpOnly cookie | None (JS can't read) | Medium | Best for refresh tokens |

**Recommended pattern for the admin UI:**
1. Store access token in a JavaScript closure (memory only) — lost on page refresh, which is acceptable for a dev tool.
2. Store refresh token in an HttpOnly, SameSite=Strict cookie — survives page refresh without XSS exposure.
3. On page load, call `/auth/refresh` using the cookie to get a new access token.

**For the API client SDK (`api_client.py`):**
The current implementation stores tokens in instance attributes (`self._tokens`), which is correct — Python process memory is not XSS-accessible.

### 5. Security Headers

Add these response headers to all API responses:

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"  # Deprecated but safe to set
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if os.environ.get("ARCHON_REQUIRE_HTTPS") == "true":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

### 6. Account Lockout

**Priority: Medium** — defense-in-depth alongside rate limiting.

```python
# Track failed attempts per username in the database or in-memory
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15

# In login handler, before password check:
if user and user.failed_attempts >= MAX_FAILED_ATTEMPTS:
    if within_lockout_window(user.last_failed_at, LOCKOUT_DURATION_MINUTES):
        raise LiveAPIError(429, "ACCOUNT_LOCKED",
            f"Account locked. Try again in {remaining_minutes} minutes.")
```

---

## Hardening for Production

If Archon is ever deployed beyond localhost, address these items:

### Persistent Token Blacklist

Replace the in-memory `set` with SQLite storage:

```sql
CREATE TABLE revoked_tokens (
    token_hash TEXT PRIMARY KEY,  -- SHA256 of the token, not the token itself
    revoked_at TEXT NOT NULL,
    expires_at TEXT NOT NULL       -- Auto-cleanup: DELETE WHERE expires_at < NOW
);
```

Store only the hash of revoked tokens — if the database leaks, tokens aren't directly reusable.

### Secret Key Management

**Current behavior** (`auth/config.py:14-15`): If `ARCHON_SECRET_KEY` is not set, a random key is generated at startup. This means:
- Every restart invalidates all existing tokens.
- Multiple processes can't share tokens.

**For production:**
- Always set `ARCHON_SECRET_KEY` explicitly.
- Use at least 256 bits of entropy: `python -c "import secrets; print(secrets.token_hex(32))"`.
- Rotate the key periodically by supporting `ARCHON_SECRET_KEY_PREVIOUS` for graceful rollover.

### Audit Logging

Log security-relevant events to a structured format:

```python
EVENTS_TO_LOG = [
    "user.registered",
    "user.login.success",
    "user.login.failed",
    "user.token.refreshed",
    "user.logout",
    "user.role.changed",
    "user.deactivated",
    "auth.token.expired",
    "auth.token.revoked",
]
```

---

## Environment Configuration

### Required Variables

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `ARCHON_SECRET_KEY` | JWT signing key | Random (regenerated on restart) | **Yes** for production |

### Optional Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `ARCHON_CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:8420,http://localhost:8000` |
| `ARCHON_REQUIRE_HTTPS` | Enable HTTPS redirect and HSTS | `false` |
| `ARCHON_ACCESS_TOKEN_MINUTES` | Access token TTL | `30` |
| `ARCHON_REFRESH_TOKEN_DAYS` | Refresh token TTL | `7` |
| `ARCHON_DB_PATH` | Path to auth SQLite database | `.orchestra/auth.db` |
| `ARCHON_BCRYPT_ROUNDS` | bcrypt work factor | `12` |
| `ARCHON_MIN_PASSWORD_LENGTH` | Minimum password length | `8` |

### Example `.env` File

```bash
# .env — NEVER commit this file
ARCHON_SECRET_KEY=a1b2c3d4e5f6... # Generate: python -c "import secrets; print(secrets.token_hex(32))"
ARCHON_CORS_ORIGINS=http://localhost:8420,http://localhost:8000
ARCHON_REQUIRE_HTTPS=false
ARCHON_ACCESS_TOKEN_MINUTES=30
ARCHON_REFRESH_TOKEN_DAYS=7
```

---

## Deployment Checklist

### Pre-Deployment

- [ ] `ARCHON_SECRET_KEY` is set explicitly (not auto-generated)
- [ ] `.env` file is listed in `.gitignore`
- [ ] No hardcoded secrets in source code
- [ ] CORS origins are restricted to known hosts
- [ ] Database file path is outside the web-accessible directory
- [ ] Python dependencies are pinned (`pip freeze > requirements.txt`)

### Security Configuration

- [ ] Rate limiting is enabled on auth endpoints
- [ ] Security headers middleware is active
- [ ] HTTPS is configured (direct TLS or reverse proxy)
- [ ] `ARCHON_REQUIRE_HTTPS=true` is set for non-localhost deployments
- [ ] Access token TTL is 30 minutes or less
- [ ] Refresh token TTL is 7 days or less
- [ ] bcrypt rounds are 12 or higher

### Authentication Verification

- [ ] Registration creates user with correct default role (VIEWER)
- [ ] First user auto-promotes to ADMIN
- [ ] Login returns valid JWT pair
- [ ] Access token expires correctly
- [ ] Refresh token rotation works (old token rejected after use)
- [ ] Logout revokes refresh token
- [ ] Protected endpoints reject requests without valid token
- [ ] Role-based endpoints enforce permission hierarchy
- [ ] Deactivated accounts cannot authenticate

### Monitoring

- [ ] Failed login attempts are logged
- [ ] Token refresh anomalies are detectable
- [ ] Database backup schedule is configured
- [ ] Error responses don't leak internal details (stack traces, SQL errors)

### Post-Deployment

- [ ] Run T5's 44 integration tests against the live environment
- [ ] Run T5's security test suite (`pytest -m security`)
- [ ] Verify CORS by attempting cross-origin request from disallowed origin
- [ ] Verify rate limits by exceeding the threshold
- [ ] Check that `/api/v1/health` returns `{"status": "healthy"}`

---

## File Reference

| File | Purpose |
|------|---------|
| `orchestrator/auth/__init__.py` | Module exports |
| `orchestrator/auth/config.py` | JWT settings, password policy, DB path |
| `orchestrator/auth/models.py` | Role enum, User dataclass, Pydantic schemas, error types |
| `orchestrator/auth/passwords.py` | bcrypt hashing (12 rounds) |
| `orchestrator/auth/tokens.py` | JWT creation, validation, revocation |
| `orchestrator/auth/middleware.py` | FastAPI dependencies: `get_current_user`, `require_role` |
| `orchestrator/auth/routes.py` | Auth router factory: register, login, refresh, logout, me |
| `orchestrator/auth/database.py` | SQLite user CRUD with indexes |
| `orchestrator/auth/error_handlers.py` | Contract-compliant error responses |
| `orchestrator/live_api.py` | Contract-compliant REST API (uses auth module) |
| `orchestrator/api_client.py` | Typed async client SDK (T1) |
| `tests/test_auth.py` | Unit tests for auth module |
| `tests/test_auth_integration.py` | 44 HTTP integration tests (T5) |
| `tests/test_security.py` | OWASP security checks (T5) |
