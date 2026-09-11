# Active Directory integration (Phase 3)

> **Slice 1 is implemented:** you can configure the AD/LDAP(S) connection, store
> it securely, run a **real** connection test, and manage allowed AD groups.
> **Slice 2 (next):** wiring FreeRADIUS to authenticate RADIUS logins against
> this AD. Until then, AD settings are stored and testable but not yet used for
> RADIUS authentication (the UI says so).

## Configure (UI: Active Directory)

| Field | Example | Notes |
|-------|---------|-------|
| Domain | `corp.example.local` | AD DNS domain |
| Primary / Secondary DC | `dc01.corp.example.local` | Tried in order during the test |
| Port | `389` / `636` | 636 for LDAPS |
| Use LDAPS | on | TLS to the DC |
| Verify TLS certificate | on | **Keep on in production.** A warning is shown if off |
| Base DN | `DC=corp,DC=example,DC=local` | Search base |
| Bind User | `svc-radius@corp.example.local` | UPN or full DN |
| Bind Password | — | Stored **encrypted at rest** (Fernet); never returned or logged |
| Timeout (s) | `5` | Connect/receive timeout |
| Enabled | on | Marks AD active |

Click **Test Connection** to perform a real bind against a DC and verify the
base DN is readable. Failures return a clear reason (e.g. TLS error, bad
credentials, timeout) without leaking the password.

## Allowed AD groups

Add the AD groups permitted (or denied) to authenticate, by DN:

```
Name:      Horizon-Users
Group DN:  CN=Horizon-Users,OU=Groups,DC=corp,DC=example,DC=local
Access:    Allow
Attribute: User        (optional; used when policies are wired in slice 2)
```

## Security

- Bind password encrypted at rest (Fernet), like RADIUS shared secrets — never
  returned by the API/UI, never logged, never exported by default.
- All host/DN inputs are validated (no control characters) since they will feed
  a generated FreeRADIUS `ldap` module in slice 2.
- The connection test builds no LDAP filter from user input, so it is not
  susceptible to LDAP injection.
- LDAPS certificate validation is on by default; disabling it shows a warning.

## What slice 2 adds

- A generated FreeRADIUS `ldap` module + PAP-over-LDAP authenticate flow.
- Group authorization: only members of the allowed groups get `Access-Accept`.
- The control agent extended to manage these files and reload safely.
- The built-in end-to-end **Test Authentication** (Phase 4) then exercises the
  full Horizon → RADIUS → AD chain.
