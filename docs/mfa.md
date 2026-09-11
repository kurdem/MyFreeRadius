# Multi-Factor Authentication (TOTP) — Phase 4

Adds a real second factor (time-based one-time password) to RADIUS logins,
self-contained in the appliance — no external MFA provider required.

## How it works

When MFA is **enabled** and the configuration is **activated**, FreeRADIUS stops
doing the auth itself and delegates to this appliance via `rlm_rest`:

```
Horizon ──RADIUS──▶ FreeRADIUS (manager site) ──HTTPS rlm_rest──▶ Manager backend
                                                                    ├─ verify TOTP
                                                                    └─ (append mode) AD bind + group check
```

The backend endpoint `POST /api/v1/radius/authorize` is authenticated by the
shared `RADIUS_AGENT_TOKEN` (sent in the request body, internal network only)
and returns HTTP 200 (Access-Accept) or 401 (Access-Reject). Passwords and OTPs
are never logged; TOTP secrets are stored **encrypted at rest** (Fernet).

## Modes

| Mode | RADIUS passcode | Who checks the AD password |
|------|-----------------|----------------------------|
| **totp_only** (recommended) | the 6-digit OTP | Horizon (Windows auth) |
| **ad_password_plus_totp** | `<AD-password><6-digit OTP>` | this appliance (LDAP bind) |

* **totp_only**: Horizon is configured to validate Windows credentials against
  AD itself, and RADIUS provides only the second factor. This matches the usual
  "enter your Windows password *and* a passcode" Horizon flow.
* **ad_password_plus_totp**: the whole check happens in RADIUS. The user appends
  the 6-digit code to their AD password. Group membership and the AD password
  are verified by the appliance.

In both modes only users with a **confirmed** TOTP token are accepted; a user
without an enrolled token is rejected.

## Enroll a user

1. **MFA** page → enter the AD `sAMAccountName` → **Generate token**.
2. Scan the QR code with an authenticator app (Microsoft Authenticator, Google
   Authenticator, …) — or type the manual key.
3. Enter a current 6-digit code → **Confirm**. The token is now active.

The name shown next to the account in the authenticator app (the "issuer") is
configurable under **Branding → OTP issuer** — set it to your company name or a
label. It defaults to `FreeRADIUS Manager` and applies to new enrollments.

## Enable it

1. **MFA** page → **Enable MFA**, choose the mode, **Save**.
2. **Configuration → Generate Candidate** — the preview now shows
   `mods-enabled/rest` and a `manager` site that delegates to the backend.
3. **Validate** → **Activate**.

> The generated FreeRADIUS config is validated by `freeradius -XC` on activate,
> with automatic rollback if it fails.

## Horizon configuration

- **totp_only**: In the Horizon Connection Server RADIUS settings, keep Windows
  authentication on and RADIUS as the second factor. The RADIUS "passcode" the
  user enters is the OTP.
- **ad_password_plus_totp**: The user enters AD password immediately followed by
  the 6-digit code as the RADIUS passcode.

## Security notes

- TOTP secrets encrypted at rest; never returned by the API after enrollment
  (only shown once, at enrollment, for the QR/manual key).
- The RADIUS-facing endpoint is token-authenticated and internal-only; it is not
  a session/cookie endpoint.
- Enrollment requires proving a valid code (confirm) before MFA is enforced for
  that user, preventing lockouts from mistyped secrets.
