# Backup & Restore (Phase 5)

Export and restore the full application configuration from the **Backup** page.

## What's included
RADIUS clients, client groups, Active Directory config, allowed AD groups, MFA
settings + TOTP tokens, CA certificates, and local user accounts.

**Not** included: the audit log and the generated config-version history (both
are append-only / regenerable).

## Secrets
Shared secrets, the AD bind password and TOTP secrets are exported **as stored
ciphertext** (Fernet). A backup therefore only restores usefully on a server
with the **same `FERNET_KEY`**. Keep `FERNET_KEY` safe and unchanged — without
it, restored secrets cannot be decrypted.

Optionally set a **passphrase** when creating a backup to encrypt the whole file
(scrypt-derived key + Fernet). The same passphrase is required to restore it.

## Create a backup
Backup page → optional passphrase → **Download backup**. A timestamped
`freeradius-manager-backup-*.json` (or `*.enc.json`) file is downloaded.

## Restore a backup
> **Destructive** — replaces all current configuration.

1. Backup page → **Choose backup file** → enter the passphrase if it is encrypted.
2. **Restore**.
3. Go to **Configuration → Generate → Validate → Activate** to apply the restored
   config to FreeRADIUS.
4. You may need to log in again (local users are restored too).

If the backup was created with a different `FERNET_KEY`, restore is refused
(its secrets would be unusable). You can override with **Force**, but the
encrypted secrets will not work until you re-enter them.

## Command-line alternative
A raw PostgreSQL dump also works for disaster recovery:
```bash
docker compose exec database pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
```
