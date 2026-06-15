# Security Model

## Current State (Proof of Concept)

This is a localhost-only proof of concept. There is **no authentication or authorization**.

### Known Gaps (P0)

1. **No Authentication**: All endpoints are unauthenticated. Anyone with network access to the backend can:
   - View/modify runs
   - Upload/delete WAD files
   - Access system settings
   - View recordings and reports

2. **Credential Exposure**: 
   - `GEMINI_API_KEY` stored in plaintext in `Backend/.env`
   - No encryption at rest for API keys
   - `.env` in `.gitignore` but no other protection
   - Database credentials in plaintext in `.env`

3. **No HTTPS/TLS**: All traffic is plain HTTP and WebSocket (ws://).

4. **No Rate Limiting on API Endpoints**: While LLM calls are rate-limited, HTTP endpoints have no protection against abuse.

5. **No Input Validation on Uploads**:
   - WAD files stored as-is on disk
   - No sanitization of filenames beyond basic validation
   - No file type verification beyond `.wad` extension

## Mitigations

### File System

- `path_security.py`: `resolve_path_within()` validates paths stay within configured storage directories
- `unlink_if_within()`: Safe file deletion that refuses to delete outside allowed paths
- Storage directories in `Settings`: All paths must resolve within `STORAGE_BASE`

### Secrets

- `.env` excluded from git via `.gitignore`
- Docker environment variables passed at runtime (not baked into images)
- `GEMINI_API_KEY` optional: system falls back to deterministic behavior without it

### Database

- PostgreSQL advisory lock prevents concurrent runs (single-active-run constraint)
- SQLAlchemy parameterized queries prevent injection
- Alembic migrations versioned and reviewed

### LLM Guard System

- Guard validates LLM decisions before MCP execution
- `guard_modified` flag tracks when guard intervenes
- Prevents obviously invalid action parameters
- Falls back to deterministic behavior if LLM is unavailable

## Recommendations for Production

| Priority | Item | Description |
|----------|------|-------------|
| P0 | API Authentication | API key or OAuth2 for all endpoints |
| P0 | Secrets Management | Vault/password manager for API keys |
| P0 | HTTPS/TLS | Certificates for all services |
| P1 | Rate Limiting | Per-IP throttling on API endpoints |
| P1 | Input Validation | WAD file validation + antivirus scan |
| P1 | CORS Restrictions | Tighten CORS to specific origins |
| P1 | Session Management | User sessions for WebSocket connections |
| P2 | Audit Logging | Access logs for all data mutations |
| P2 | Data Encryption | Encrypt recordings and reports at rest |
| P2 | Container Security | Non-root users, read-only filesystems |
| P3 | Network Isolation | Service mesh / separate network namespaces |

## Current Best Practices Applied

- `.env` and `.venv` in `.gitignore`
- Path traversal protection for file operations
- Parameterized SQL queries via SQLAlchemy
- LLM input sanitization (`_sanitize_prompt_value`)
- Report voice sanitization removes agent blame phrases
- Process-local task registry (no cross-replica concerns for single-instance)
- Sentry error tracking (opt-in, traces_sample_rate=0.1)
