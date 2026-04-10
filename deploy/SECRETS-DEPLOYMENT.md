# Deploying the encrypted secrets vault to the live server

This is the runbook for migrating an existing PSA Dashboard install to the
encrypted credentials vault. After this migration, API tokens are no longer
stored in plaintext in `config.yaml`. They live in an AES-256-GCM encrypted
SQLite table and are managed through the dashboard's Settings page behind a
password.

If this is a fresh install with no prior `config.yaml`, skip to
[Fresh installs](#fresh-installs) at the bottom.

**Time required:** about 20 minutes of active attention. Block out the time
in advance and do not start this when you might get interrupted. Steps 3
through 5 must run consecutively.

## Quick walkthrough (do this on migration day)

This is the linear path. The sections below it explain what each step does
and what to do when something goes wrong. Read this section start to finish
before you SSH in, then follow it step by step.

### Before you SSH in

Have these ready in a window you can reach without leaving your terminal:

- **Your password manager, unlocked.** You will add 2 new entries during
  this migration.
- **A new strong admin password generated and on your clipboard.** At least
  12 characters. Generate it from your password manager now, do not make
  one up at the keyboard mid-migration.

### Step 1: SSH in and back up

```bash
ssh intadmin@your-server-ip
cd /path/to/psa-dashboard          # wherever install.sh was run

cp config.yaml ~/config.yaml.backup-$(date +%Y%m%d)
cp backend/data/metrics.db ~/metrics.db.backup-$(date +%Y%m%d)
ls -la ~/config.yaml.backup-* ~/metrics.db.backup-*
```

The metrics.db copy is a few MB but gives you total rollback safety.
Worth it.

### Step 2: Open journalctl in a SECOND terminal

Open a separate SSH session in a new terminal window so you can watch the
logs while the update runs in the first window.

```bash
sudo journalctl -u psa-dashboard -f
```

Leave this running. Do not close it. The migration will scroll through
here.

### Step 3: Run the update (in the first terminal)

```bash
sudo bash update.sh
```

You will see, in order:
1. `Pulling latest code...`
2. `Python dependencies changed, installing...` (cryptography, bcrypt,
   itsdangerous; takes about 30 seconds)
3. `Frontend changed, rebuilding...` (the React build, about 30-60 seconds)
4. `Restarting service...`
5. `Done. Dashboard is updated and running.`

### Step 4: Watch the journalctl window

Within a few seconds of the restart you should see, in order:

```
Starting PSA Dashboard
Database initialized at data/metrics.db
Generated new vault master key at data/.vault_master_key. BACK THIS FILE UP...
vault: migrated 8 secret(s) from .../config.yaml into the encrypted store
vault: original plaintext yaml backed up at .../config.yaml.pre-secrets.bak
PSA providers: superops, zendesk
Sync scheduler started
Phone provider: Zoom Phone
```

The number of migrated secrets should be **8** (matching the test computer
migration). Within the next 5 to 10 seconds you should also see successful
upstream API calls:

```
POST https://api.superops.ai/msp "HTTP/1.1 200"
POST https://zoom.us/oauth/token "HTTP/1.1 200 OK"
[superops] Synced N technicians
```

That confirms the providers are reading credentials from the vault and
authenticating. **If you see `migrated 0` and `skipped 8`, STOP and roll
back** (see [Rollback](#rollback) below). Do not proceed until you
understand why nothing migrated.

### Step 5: Back up the master key (CRITICAL, do not skip)

In the first terminal:

```bash
sudo cat backend/data/.vault_master_key
```

You will see a single line of base64. **Select it, copy it, paste it into
your password manager** as a new entry labeled `PSA Dashboard PROD master
key`. This is the only thing that can decrypt your stored credentials. If
this file is ever lost or the disk dies and you do not have this backup,
your stored credentials are unrecoverable and you will have to re-enter
every API token through the Settings UI.

### Step 6: Delete the plaintext backup file

The migration created a one-time backup of your original `config.yaml`
that still contains your plaintext API tokens. Delete it now that you have
verified the migration succeeded:

```bash
sudo rm config.yaml.pre-secrets.bak
ls config.yaml*    # should show only config.yaml (and your earlier ~/backup)
```

### Step 7: Set the admin password in the browser

Open `http://your-server-ip:5051/settings` in your browser. You will see
the **Set Admin Password** form (because no admin user exists yet on the
live server's database).

1. Paste the strong password you generated in your clipboard
2. Confirm it
3. Click **Create admin and continue**
4. **Save this password in your password manager** as a separate entry
   labeled `PSA Dashboard PROD admin login`. It is a different secret
   from the master key.

You should land on the Settings page proper with three provider cards
(SuperOps, Zendesk, Zoom Phone) all showing **Configured**. The text
fields (subdomain, email) should be pre-filled with your actual values.

### Step 8: Smoke test

In the browser:

- Navigate to Overview, Tickets, Phone Analytics, Manage to Zero — they
  should all load with your real data, no errors
- Click **Test connection** on each of the three provider cards in
  Settings. You should see a green check and a count: "Connected, found N
  technicians" or "Connected, found N users"
- Scroll to the bottom of Settings and check the **Audit Log** table.
  You should see 8 entries with action `set` and actor `migrate`, plus
  one entry with actor `admin` for your password setup

### Step 9: Cleanup (optional, do this a day or two later)

After you have used the dashboard for at least a day and confirmed
everything is solid, log into the server and trim the stale placeholders
from your live `config.yaml`. They are harmless (the factory ignores
them) but they are noise:

```bash
sudo nano /path/to/psa-dashboard/config.yaml
```

Remove these lines (they are now in the vault, the entries are just
leftover placeholders):

- `psa.superops.api_token: __stored_in_db__`
- `psa.superops.subdomain: __stored_in_db__`
- `psa.zendesk.subdomain: __stored_in_db__`
- `psa.zendesk.email: __stored_in_db__`
- `psa.zendesk.api_token: __stored_in_db__`
- `phone.zoom.account_id: __stored_in_db__`
- `phone.zoom.client_id: __stored_in_db__`
- `phone.zoom.client_secret: __stored_in_db__`

Also remove these blocks if present, they are unused:

- The entire `database:` section (the default value matches)
- The `halopsa:` stub
- The `phone.zoom:` empty block (leave `phone.provider: zoom`)

Then restart and verify:

```bash
sudo systemctl restart psa-dashboard
sudo journalctl -u psa-dashboard -f --since "30 seconds ago"
```

You want to see "vault: nothing to migrate (skipped 8 keys)" and the
sync running normally with no errors.

---

## Reference: details on each phase

The sections below explain in more depth what each step does, what can go
wrong, and how to recover. Read these only if you hit a problem during
the walkthrough above.

## Before you start

1. **Confirm you are the only person with shell access to the VM.** SSH
   should already be locked down to your account. If you are not sure, run
   `grep AllowUsers /etc/ssh/sshd_config` and verify only your username is
   listed.

2. **Back up `config.yaml` to your workstation.** This is your safety net if
   anything goes sideways.
   ```bash
   scp psa-dashboard-server:/path/to/psa-dashboard/config.yaml ./config.yaml.backup
   ```

3. **Back up `backend/data/metrics.db` to your workstation.** Larger file,
   but cheap insurance.
   ```bash
   scp psa-dashboard-server:/path/to/psa-dashboard/backend/data/metrics.db ./metrics.db.backup
   ```

4. **Open a terminal where you can watch the logs in real time.** You will
   want to see what happens during the first restart.
   ```bash
   sudo journalctl -u psa-dashboard -f
   ```
   Leave this running in one window. Open a second window for the actual
   deployment.

## The deployment

Everything happens in `update.sh`, which `git pull`s, installs new Python
dependencies, rebuilds the frontend if needed, and restarts the systemd
service. The migration runs automatically the first time the new code
boots.

```bash
cd /path/to/psa-dashboard
sudo bash update.sh
```

You will see, in roughly this order:
1. `Pulling latest code...`
2. `Python dependencies changed, installing...` (cryptography, bcrypt, itsdangerous)
3. `Frontend changed, rebuilding...`
4. `Restarting service...`
5. `Done. Dashboard is updated and running.`

## What to watch for in the logs

In your `journalctl` window you should see, in order:

```
Starting PSA Dashboard
Database initialized at data/metrics.db
Generated new vault master key at data/.vault_master_key. BACK THIS FILE UP...
vault: migrated N secret(s) from .../config.yaml into the encrypted store
vault: original plaintext yaml backed up at .../config.yaml.pre-secrets.bak
PSA providers: superops, zendesk     (or whatever you have configured)
Sync scheduler started
```

The number `N` will be however many credential fields you currently have
in `config.yaml`. For a typical SuperOps + Zendesk + Zoom Phone install,
that is 8 fields.

If you see `vault: nothing to migrate` and N is 0, that means the credentials
were not in the form the migration expects. Stop here, restore your backups,
and contact the maintainer.

## Immediately after the restart succeeds

These three things should happen within five minutes of the restart, in this
order. Do not skip any of them.

### 1. Back up the master key file

```bash
sudo cat /path/to/psa-dashboard/backend/data/.vault_master_key
```

You will see a single line of base64. **Copy that line and paste it into
your password manager** as a secure note labeled something like
"PSA Dashboard PROD master key". This is the only key that can decrypt your
stored credentials. If the file is ever lost or the disk dies, your stored
credentials are gone unless you have this backup.

### 2. Delete the plaintext backup file

The migration created a one-time backup of your original `config.yaml` at
`config.yaml.pre-secrets.bak`. This file still contains your plaintext API
tokens. Delete it now that you have verified the dashboard works:

```bash
sudo rm /path/to/psa-dashboard/config.yaml.pre-secrets.bak
```

### 3. Set the admin password

Open the dashboard in your browser at `http://your-server-ip:5051` and
click **Settings** in the sidebar. You will see a "Set Admin Password" form.
Pick a strong password (at least 12 characters), confirm it, click create.

**Save this password in your password manager** as a separate entry from
the master key.

After the form submits, you should land on the Settings page proper and
see all your credential fields listed as **Configured**. The text fields
(SuperOps Subdomain, Zendesk Subdomain, Zendesk Email) will be pre-filled
with their actual values. The token fields will show as masked.

## Verification

The migration is successful when ALL of these are true:

- [ ] `journalctl` showed `vault: migrated N secret(s)` with N matching the
      number of credential fields you had
- [ ] `cat /path/to/psa-dashboard/config.yaml` shows `__stored_in_db__`
      placeholders where your API tokens used to be
- [ ] `ls /path/to/psa-dashboard/backend/data/.vault_master_key` exists
- [ ] You backed up the master key to your password manager
- [ ] You deleted `config.yaml.pre-secrets.bak`
- [ ] The Settings page shows all credentials as Configured
- [ ] The dashboard at `http://your-server-ip:5051` still loads tickets,
      clients, and phone data normally
- [ ] `journalctl -u psa-dashboard -f` shows the next scheduled sync running
      successfully (HTTP 200 from SuperOps / Zendesk / Zoom)

## Rollback

If anything looks wrong, roll back BEFORE clearing your backups.

```bash
# Stop the service
sudo systemctl stop psa-dashboard

# Restore the original config.yaml
sudo cp /path/to/your/backup/config.yaml.backup /path/to/psa-dashboard/config.yaml
sudo chown $(stat -c '%U' /path/to/psa-dashboard):$(stat -c '%U' /path/to/psa-dashboard) /path/to/psa-dashboard/config.yaml

# Restore the original metrics.db (optional, only if vault tables cause problems)
sudo cp /path/to/your/backup/metrics.db.backup /path/to/psa-dashboard/backend/data/metrics.db

# Roll the code back to the previous commit
cd /path/to/psa-dashboard
sudo -u $(stat -c '%U' .) git log --oneline -10    # find the previous commit
sudo -u $(stat -c '%U' .) git checkout <previous-commit-sha>

# Reinstall the older Python deps and frontend, then restart
sudo bash update.sh
```

## Recovery scenarios

### "I forgot the admin password"

Reset it from the server command line. There is no email recovery.

```bash
cd /path/to/psa-dashboard/backend
sudo -u $(stat -c '%U' .) ./.venv/bin/python -m app.vault.cli set-admin-password
```

It will prompt for the new password (hidden input) and confirm. The session
cookie from the old password is invalidated automatically since the hash in
the database changes.

### "I lost the master key file"

If `backend/data/.vault_master_key` is gone and you do not have a backup,
the encrypted credentials are unrecoverable. You will need to:

1. Stop the service
2. Drop the vault tables to start fresh:
   ```bash
   sqlite3 backend/data/metrics.db <<EOF
   DELETE FROM vault_secrets;
   DELETE FROM vault_meta;
   EOF
   ```
3. Start the service. It will generate a new master key.
4. Open Settings and enter your API tokens, subdomains, and email manually.
5. Back up the new master key.

This is annoying but not catastrophic. Your tickets and dashboard data are
unaffected; only the stored credentials have to be re-entered.

### "I need to rotate the master key (advanced)"

Only relevant if you have moved the master key off disk into the
`PSA_DASHBOARD_MASTER_KEY` environment variable for stricter compliance.

```bash
cd /path/to/psa-dashboard/backend
./.venv/bin/python -m app.vault.cli generate-kek           # prints a new key
PSA_DASHBOARD_MASTER_KEY_NEW=<new key> \
PSA_DASHBOARD_MASTER_KEY=<old key> \
./.venv/bin/python -m app.vault.cli rotate-kek
```

After this completes, update your systemd `EnvironmentFile` to use the new
key value and restart the service.

### "I need to rotate an API token because we are offboarding a tech"

This is the case the Settings UI was built for.

1. Generate the new token in SuperOps / Zendesk / Zoom admin
2. Open the dashboard, go to Settings
3. Paste the new token into the matching field, click Save
4. The backend hot-reloads the affected provider in place. No restart
   required.
5. Verify the next sync succeeds in `journalctl`

## Compliance notes

- **Encryption:** AES-256-GCM, FIPS 197 approved. Per-record nonce, key
  name bound as Additional Authenticated Data so a row swap attack is
  detected. Satisfies CJIS 5.10.1.2.1 (key length), HIPAA 164.312(a)(2)(iv)
  addressable encryption, CMMC SC.L2-3.13.11.

- **FIPS module caveat:** the `cryptography` Python library uses OpenSSL.
  CMMC and CJIS auditors typically require a FIPS 140-2/140-3 **validated**
  module, not just a FIPS-approved algorithm. On stock Ubuntu this is not
  the case. To fully claim the control, deploy on Ubuntu Pro FIPS so
  OpenSSL runs in FIPS mode. The application code does not need to change.

- **Audit log:** all credential mutations (set, delete, password change)
  are recorded in the `secrets_audit` SQLite table with timestamp, actor,
  action, key name, IP address, and user agent. Visible in the Settings UI
  and queryable via `GET /api/admin/audit`. Read access is NOT logged
  because every page render of the dashboard would trigger one and bury the
  real activity.

- **Key storage:** by default the master key lives at
  `backend/data/.vault_master_key` with mode 0600 (POSIX). This is
  sufficient when SSH access to the VM is restricted to the dashboard
  admin only. For environments where multiple operators have shell access,
  move the key off disk into the `PSA_DASHBOARD_MASTER_KEY` environment
  variable and document the systemd `EnvironmentFile` configuration.

- **Residual risk for ticket data:** `tickets`, `phone_calls`, `clients`,
  and `client_contracts` tables in `metrics.db` remain plaintext. If any of
  this data is ePHI or CJI for one of your clients, follow up with a
  SQLCipher migration to encrypt the entire database file at rest. As an
  interim mitigation, place `backend/data/` on a LUKS-encrypted volume.

- **Backups:** `metrics.db` and `backend/data/.vault_master_key` MUST be
  backed up together. A backup of one without the other is useless.

## Fresh installs

If you are setting up the dashboard from scratch on a new server (no
existing `config.yaml`), the flow is simpler:

1. Run `sudo bash install.sh` as documented in the main README. This
   creates a `config.yaml` from `config.example.yaml`.
2. Edit `config.yaml` and fill in the **non-secret** fields only:
   - `psa.providers`
   - `psa.superops.api_url` (defaults to the right value)
   - `phone.provider`
   - `server.timezone`, `business_hours`, `thresholds`, `billing`
   - Any complex Zendesk fields: `ticket_url_template`, `extra_agents`,
     `tech_merge_map`, `exclude_custom_fields`, `status_display_overrides`
3. Restart the service: `sudo systemctl restart psa-dashboard`
4. Open the dashboard, click Settings, set the admin password, then enter
   your subdomains, emails, and API tokens through the UI.
5. Back up `backend/data/.vault_master_key` to your password manager.

You never put plaintext credentials in `config.yaml` on a fresh install.
