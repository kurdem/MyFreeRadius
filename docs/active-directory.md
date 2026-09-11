# Active Directory integration (Phase 3)

> **Slices 1 & 2 are implemented:** configure and **test** the AD/LDAP(S)
> connection, manage allowed AD groups, and — when AD is **enabled** and the
> configuration is activated — FreeRADIUS authenticates RADIUS logins against AD
> (PAP bind) with AD group authorization.

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

## How authentication is wired (slice 2)

When AD is **enabled** and you **activate** the configuration, the generator
produces a bundle that the control agent validates with `freeradius -XC`, writes,
and reloads (rolling everything back if validation/reload fails):

| File | Purpose |
|------|---------|
| `mods-enabled/ldap` | LDAP module pointed at your DC(s), base DN and bind user |
| `sites-enabled/manager` | Virtual server: `ldap` lookup → AD group check → PAP bind as the user |
| `sites-enabled/default` (removed) | Replaced by `manager` while AD is enabled (they would clash on 1812/1813) |

Authentication uses **PAP bind**: FreeRADIUS finds the user by `sAMAccountName`
and binds to AD with the supplied password. Horizon must therefore be set to
**PAP** for now (see [horizon.md](horizon.md)); MS-CHAPv2 needs ntlm_auth/winbind
and is a later addition.

Group authorization: only members of an **allow** group get `Access-Accept`;
**deny** groups are rejected first. With no allow-groups defined, any
authenticated AD user is accepted.

> The generated FreeRADIUS config follows the standard FR 3.x AD/LDAP recipe and
> is validated by `freeradius -XC` in your environment on every activate; a
> failed validation never replaces the working config. If your AD schema differs
> (e.g. login attribute), adjust and re-activate.

## Activate

1. Configure AD, set **Enabled**, and **Test Connection**.
2. Add the allowed AD group(s).
3. **Configuration → Generate Candidate** (preview shows `ldap` + `manager`),
   **Validate**, then **Activate**.
4. A real login from Horizon/UAG now authenticates against AD.

Rebuild note: the FreeRADIUS image needs `ldap` support (present in the
`freeradius/freeradius-server` image). No image change is required to enable AD;
the module is generated and written at activation time.
