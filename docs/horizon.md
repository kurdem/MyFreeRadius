# VMware Horizon integration

This guide separates **Horizon-side** configuration from **FreeRADIUS-side**
configuration. FreeRADIUS Manager handles the FreeRADIUS side; the RADIUS
settings on the Connection Server are done in the Horizon Console.

```
Horizon Client ─▶ Connection Server ─RADIUS/1812─▶ FreeRADIUS ─LDAP(S)─▶ Active Directory
```

## FreeRADIUS side (this application)

1. **RADIUS Clients → Add Client** for each Connection Server:
   - **Name**: e.g. `Horizon-CS01`
   - **IP address**: the Connection Server's IP (the source of RADIUS packets),
     e.g. `10.10.20.11`
   - **Shared secret**: a strong secret (8–128 chars, no quotes/backslashes/spaces)
   - **NAS Type**: `vmware`
2. Optionally group multiple Connection Servers (e.g. `Horizon Cluster Siegen`)
   under **Client Groups**.
3. **Configuration → Generate Candidate → Validate → Activate**.

> The Connection Server's IP must match the RADIUS source IP FreeRADIUS sees.
> If Connection Servers sit behind NAT/load balancers, use the address packets
> actually originate from (a CIDR is allowed).

## Horizon side (VMware Horizon Console)

On the Connection Server (**Settings → Servers → Connection Servers → Edit →
Authentication**, or the 2-factor authentication settings), configure a RADIUS
authenticator:

| Field | Value |
|-------|-------|
| Authentication type | RADIUS |
| Hostname/Address | IP of the host running FreeRADIUS Manager |
| Authentication port | 1812 |
| Accounting port | 1813 (optional) |
| Shared secret | the same secret you set for this client |
| Authentication protocol | see below |
| Server timeout | e.g. 5 seconds |
| Max retries | e.g. 3 |

For resilience, add **two RADIUS servers** (primary/secondary) in Horizon when
you run more than one FreeRADIUS instance.

## Authentication protocol

Horizon supports **PAP**, **CHAP**, **MS-CHAPv2** between the Connection Server
and RADIUS. Which one you can use depends on how FreeRADIUS authenticates the
user against Active Directory (Phase 3):

| RADIUS protocol | Works with AD via… | Notes |
|-----------------|--------------------|-------|
| **PAP** | LDAP bind / `ldap` | Simplest; the shared secret + TLS protect the tunnel. Recommended starting point. |
| **MS-CHAPv2** | `ntlm_auth` / winbind against AD | No cleartext password to AD, but requires domain join / winbind. |

> The UI will document these constraints per configuration once AD integration
> lands. We will **not** advertise a protocol the configured AD backend cannot
> actually perform.

## Testing the chain

- **Now (Phase 2):** use `radclient`/`radtest` from any host, or watch the
  **Logs** page, to confirm RADIUS transport + shared secret:
  ```bash
  echo "User-Name=test,User-Password=test" | \
    radclient -x <freeradius-host>:1812 auth <shared-secret>
  ```
  Without AD configured this returns `Access-Reject` (expected) but proves the
  client/secret are correct.
- **Phase 4:** the built-in **Test Authentication** page will perform a real
  end-to-end test against a policy and AD.

## Common issues

| Symptom | Likely cause |
|---------|--------------|
| No log entry on the Logs page | Packet never reached FreeRADIUS: firewall/UDP 1812, wrong server IP in Horizon |
| `Access-Reject` immediately, log shows "client unknown" | Connection Server IP not registered as a RADIUS client, or config not activated |
| Reject with "Shared secret is incorrect" in debug | Secret mismatch between Horizon and the client entry |
