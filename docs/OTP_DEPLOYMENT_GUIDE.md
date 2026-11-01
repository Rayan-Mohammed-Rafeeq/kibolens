# KiboLens OTP Authentication - Deployment Guide

This guide covers deployment of the production-ready two-administrator email OTP authentication system.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [Administrator Provisioning](#administrator-provisioning)
4. [Production Deployment](#production-deployment)
5. [Resend Configuration](#resend-configuration)
6. [Testing](#testing)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Services
- PostgreSQL 17 with pgvector
- Resend account with verified sending domain
- Docker and Docker Compose

### Environment Variables
All environment variables are documented in `.env.example`. Critical variables for OTP authentication:

```bash
# Resend Email Service
RESEND_API_KEY=re_your_actual_api_key_here
KIBOLENS_EMAIL_FROM=noreply@yourdomain.com
KIBOLENS_EMAIL_REPLY_TO=support@yourdomain.com

# Administrator Allowlist
KIBOLENS_ALLOWED_EMAILS=rayanmohammedrafeeq@gmail.com,rakinmohammedrafeeq@gmail.com

# OTP Security
KIBOLENS_OTP_HASH_SECRET=64_char_hex_string
KIBOLENS_OTP_TTL_SECONDS=300
KIBOLENS_OTP_RESEND_COOLDOWN_SECONDS=60
KIBOLENS_OTP_MAX_ATTEMPTS=5

# Session Security (already configured)
KIBOLENS_SESSION_HASH_SECRET=64_char_hex_string
```

## Local Development Setup

### 1. Generate Secrets

```powershell
# On Windows with PowerShell, generate OTP hash secret:
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
-join ($bytes | ForEach-Object { $_.ToString("x2") })
```

Or on Linux/macOS:
```bash
openssl rand -hex 32
```

### 2. Configure Environment

Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

Edit `.env` and set:
- `RESEND_API_KEY` - Leave as placeholder for local development (uses MockEmailService)
- `KIBOLENS_OTP_HASH_SECRET` - Use generated secret
- Other variables as needed

### 3. Run Database Migration

```powershell
cd backend
alembic upgrade head
```

This applies migration `20261031_0003_add_email_otp.py` which:
- Adds `email` and `email_normalized` columns to `users` table
- Creates `otp_challenges` table
- Preserves existing data

### 4. Provision Administrator Accounts

Run the provisioning CLI for each administrator:

```powershell
cd backend
python -m app.cli.provision_admin
```

You'll be prompted for:
1. Email address (must be in `KIBOLENS_ALLOWED_EMAILS`)
2. Username
3. Password (minimum 14 characters, entered via secure getpass - not echoed)
4. Password confirmation

Example session:
```
Administrator Provisioning
==========================
Email: rayanmohammedrafeeq@gmail.com
Username: rayan
Password: (hidden input)
Confirm password: (hidden input)

✓ Administrator account created successfully
  Username: rayan
  Email: rayanmohammedrafeeq@gmail.com
  Role: admin
```

Repeat for second administrator:
```
Email: rakinmohammedrafeeq@gmail.com
Username: rakin
Password: (hidden)
Confirm password: (hidden)
```

### 5. Start Development Services

Without Resend API key (uses MockEmailService):
```powershell
docker-compose -f deployment/docker-compose.yml up -d
```

MockEmailService logs OTP codes to backend logs instead of sending emails:
```powershell
docker-compose -f deployment/docker-compose.yml logs -f backend
```

Look for log lines like:
```
Mock: OTP email recorded for rayanmohammedrafeeq@gmail.com
```

## Production Deployment

### 1. Resend Setup

1. Create account at [resend.com](https://resend.com)
2. Add and verify your sending domain
3. Generate API key
4. Update production `.env`:
   ```bash
   RESEND_API_KEY=re_your_production_key_here
   KIBOLENS_EMAIL_FROM=noreply@yourdomain.com
   KIBOLENS_EMAIL_REPLY_TO=support@yourdomain.com
   ```

### 2. Generate Production Secrets

**NEVER use development secrets in production.**

Generate new secrets:
```bash
openssl rand -hex 32  # For KIBOLENS_OTP_HASH_SECRET
openssl rand -hex 32  # For KIBOLENS_SESSION_HASH_SECRET (if regenerating)
```

### 3. Update Environment

On production server, edit `/path/to/kibolens/.env`:
```bash
# Environment
KIBOLENS_ENVIRONMENT=production

# Resend (PRODUCTION VALUES)
RESEND_API_KEY=re_production_key_here
KIBOLENS_EMAIL_FROM=noreply@yourdomain.com
KIBOLENS_EMAIL_REPLY_TO=support@yourdomain.com

# Administrator Allowlist
KIBOLENS_ALLOWED_EMAILS=rayanmohammedrafeeq@gmail.com,rakinmohammedrafeeq@gmail.com

# OTP Security (PRODUCTION VALUES)
KIBOLENS_OTP_HASH_SECRET=production_64_char_hex_here
```

Set restrictive permissions:
```bash
chmod 600 /path/to/kibolens/.env
```

### 4. Run Migration

**This preserves existing data.**

```bash
cd /path/to/kibolens/backend
source .venv/bin/activate  # Or activate your virtual environment
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade 20261030_0002 -> 20261031_0003, Add email and OTP authentication
```

### 5. Provision Administrators

```bash
cd /path/to/kibolens/backend
python -m app.cli.provision_admin
```

Provision both administrators as shown in Local Development Setup.

### 6. Restart Services

```bash
cd /path/to/kibolens
docker-compose -f deployment/docker-compose.yml down
docker-compose -f deployment/docker-compose.yml up -d --build
```

The `backend_egress` network allows backend to reach Resend API while keeping PostgreSQL isolated.

### 7. Test Email Delivery

1. Navigate to login page
2. Enter administrator email and password
3. Verify OTP email arrives
4. Complete authentication

Check backend logs if email doesn't arrive:
```bash
docker-compose -f deployment/docker-compose.yml logs backend | grep -i resend
```

## Resend Configuration

### Domain Verification

Resend requires domain verification before sending emails:

1. Go to Resend Dashboard → Domains
2. Click "Add Domain"
3. Enter your domain (e.g., `yourdomain.com`)
4. Add the provided DNS records:
   - MX record
   - TXT records (SPF, DKIM)
5. Wait for verification (usually minutes, can take up to 48 hours)

### API Key Management

- **Production**: Use full-access API key, stored only in production `.env`
- **Development**: Leave `RESEND_API_KEY` empty to use MockEmailService
- **Rotation**: Generate new key in Resend dashboard, update `.env`, restart backend

### Rate Limits

Resend free tier limits:
- 100 emails per day
- 3,000 emails per month

Production tier:
- Starts at 50,000 emails/month
- Scales with plan

For KiboLens with 2 administrators:
- Each login attempt = 1 email
- Each resend = 1 email
- Typical usage: < 100 emails/month

## Testing

### Automated Tests

Run comprehensive OTP test suite:
```powershell
cd backend
python -m pytest tests/test_otp_auth.py -v
```

27 tests cover:
- Both approved administrators
- Multi-admin provisioning
- Email allowlist enforcement
- Password hashing
- OTP generation and storage
- OTP verification and expiration
- Resend cooldown
- Maximum attempts
- Replay attack prevention
- Session creation only after OTP

### Manual Testing Checklist

#### Stage 1: Email/Password
- [ ] Login page displays correctly
- [ ] Email validation works
- [ ] Password visibility toggle works
- [ ] Invalid credentials show generic error
- [ ] Valid credentials advance to OTP stage
- [ ] Rate limiting works after 5 failed attempts

#### Stage 2: OTP Verification
- [ ] OTP input appears after successful password
- [ ] Masked email displays correctly
- [ ] 6-digit OTP email arrives within seconds
- [ ] Valid OTP creates authenticated session
- [ ] Invalid OTP shows error
- [ ] Expired OTP (> 5 minutes) rejected
- [ ] Replayed OTP rejected
- [ ] Max attempts (5) enforced
- [ ] Resend button works after cooldown (60 seconds)
- [ ] Resend countdown displays correctly
- [ ] Back button returns to credential stage

#### Security Checks
- [ ] OTP not visible in browser network tab
- [ ] OTP not logged to files or console
- [ ] Session cookie is HttpOnly
- [ ] Session cookie is Secure (in production)
- [ ] CSRF token required for authenticated requests
- [ ] Cannot authenticate with password alone
- [ ] Disallowed emails rejected

### Integration Test with Resend

After production deployment:

1. Configure production Resend credentials
2. Restart backend service
3. Attempt login with first administrator
4. Verify email arrives at rayanmohammedrafeeq@gmail.com
5. Complete OTP verification
6. Verify session works
7. Logout
8. Repeat for second administrator (rakinmohammedrafeeq@gmail.com)

## Troubleshooting

### Email Not Received

**Check 1: Backend logs**
```bash
docker-compose logs backend | grep -i "OTP"
```

Look for:
```
INFO: OTP sent for user <uuid>
INFO: OTP email sent successfully
```

Or errors:
```
ERROR: Resend API error: status=403
ERROR: Email service unavailable
```

**Check 2: Resend Dashboard**
- Go to Resend Dashboard → Logs
- Verify send attempt appears
- Check delivery status

**Check 3: Spam folder**
- OTP emails may be flagged as spam initially
- Add sender to whitelist

**Check 4: Domain verification**
- Resend won't send from unverified domains
- Verify DNS records are correct

### OTP Invalid or Expired

**Issue**: "Verification code has expired"
- OTP expires after 5 minutes (300 seconds)
- Request new OTP via "Resend code"

**Issue**: "Maximum verification attempts exceeded"
- Too many wrong OTP attempts (5 max)
- Request new OTP via "Resend code"

**Issue**: "This verification code has already been used"
- OTP is single-use
- Request new OTP

### Database Migration Issues

**Issue**: Migration fails with "column already exists"
```
sqlalchemy.exc.ProgrammingError: (psycopg.errors.DuplicateColumn) column "email" of relation "users" already exists
```

**Solution**: Migration has already been applied
```bash
alembic current  # Check current version
alembic history  # View migration history
```

**Issue**: Existing users have no email
- Migration adds email as nullable
- Manually update existing users or re-provision

### Authentication Loop (No Session Created)

**Symptom**: OTP verifies but login loop continues

**Cause**: Session cookie not set properly

**Check**:
1. `KIBOLENS_SESSION_COOKIE_SECURE=true` requires HTTPS
2. In development, set to `false`
3. Check browser allows cookies
4. Verify `KIBOLENS_CORS_ORIGINS` includes frontend URL

### MockEmailService in Production

**Symptom**: No emails sent in production, logs show "Mock: OTP email recorded"

**Cause**: `RESEND_API_KEY` not configured

**Solution**:
1. Set `RESEND_API_KEY` in production `.env`
2. Restart backend service
3. Verify log shows "Sending OTP email" (not "Mock:")

## Security Checklist

Before production deployment:

- [ ] Generated strong `KIBOLENS_OTP_HASH_SECRET` (64 hex chars)
- [ ] Generated strong `KIBOLENS_SESSION_HASH_SECRET` (64 hex chars)
- [ ] Set `KIBOLENS_SESSION_COOKIE_SECURE=true` in production
- [ ] Set `KIBOLENS_ENVIRONMENT=production`
- [ ] `.env` has `chmod 600` permissions
- [ ] `.env` not committed to Git (in `.gitignore`)
- [ ] Resend API key is production key, not test key
- [ ] Resend sending domain is verified
- [ ] Both administrator emails in `KIBOLENS_ALLOWED_EMAILS`
- [ ] Both administrators provisioned with strong passwords (14+ chars)
- [ ] Tested full OTP flow end-to-end
- [ ] Verified session cookies are secure
- [ ] Verified CSRF protection works
- [ ] Tested rate limiting
- [ ] Backend logs do not contain secrets or OTP codes
- [ ] PostgreSQL not exposed to internet (internal network only)
- [ ] Backend connected to `backend_egress` for Resend API access

## Architecture Summary

### Network Topology
```
Internet → Caddy (frontend_ingress) → Frontend
                                         ↓
                    Backend (kibolens network) ↔ PostgreSQL
                         ↓
            backend_egress → Resend API (HTTPS)
```

- PostgreSQL: Internal only (`kibolens` network)
- Backend: Two networks (`kibolens` + `backend_egress`)
- Frontend: Two networks (`kibolens` + `frontend_ingress`)
- No services exposed to host except Caddy on 127.0.0.1:8080

### Authentication Flow

1. **Stage 1**: User enters email + password
   - Frontend → POST `/auth/login` → Backend
   - Backend verifies credentials via `authenticate_by_email()`
   - Backend generates 6-digit OTP via `generate_otp()`
   - Backend creates `OTPChallenge` with HMAC digest
   - Backend sends OTP email via Resend
   - Backend returns masked email + cooldown

2. **Stage 2**: User enters OTP from email
   - Frontend → POST `/auth/verify-otp` → Backend
   - Backend verifies OTP via `verify_otp()` (constant-time HMAC comparison)
   - Backend marks challenge as consumed
   - Backend creates session
   - Backend sets HttpOnly cookie
   - Backend returns user + CSRF token
   - Frontend redirects to dashboard

### Security Properties

- **Fail-closed**: No authentication without successful OTP verification
- **Constant-time comparison**: Prevents timing attacks
- **Single-use OTP**: Cannot replay the same code
- **Time-limited**: 5-minute expiration
- **Attempt-limited**: 5 wrong attempts max
- **Resend cooldown**: 60 seconds between sends
- **Allowlist enforcement**: Only approved emails can provision accounts
- **Password-only never sufficient**: OTP always required
- **HMAC storage**: Never stores plaintext OTP
- **No secret logging**: OTPs and secrets never logged

## Support

For issues or questions:
1. Check logs: `docker-compose logs backend`
2. Verify environment variables in `.env`
3. Run test suite: `pytest tests/test_otp_auth.py`
4. Review this guide
5. Check Resend dashboard for email delivery status

## References

- [Resend Documentation](https://resend.com/docs)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- KiboLens `ARCHITECTURE.md` for system overview
