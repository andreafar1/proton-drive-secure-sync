## Native Ubuntu LXC (Proxmox) installation — no Docker

Inside an Ubuntu LXC container running systemd, download and **review** the installer:

```bash
apt update && apt install -y git
git clone https://github.com/andreafar1/proton-drive-secure-sync.git /tmp/pdss-installer
less /tmp/pdss-installer/install-lxc.sh
bash /tmp/pdss-installer/install-lxc.sh
```

The script installs Python/Rclone, checks out the project in `/opt/proton-drive-secure-sync`, creates a `pdss` service user, Python virtual environment, two systemd services, a generated web password and session secret. It **does not start the services** until you configure Rclone. Save the printed password; it is only shown once.

```bash
sudo -u pdss env RCLONE_CONFIG=/etc/proton-drive-secure-sync/rclone.conf rclone config
sudo -u pdss env RCLONE_CONFIG=/etc/proton-drive-secure-sync/rclone.conf rclone lsd proton:
systemctl start pdss-web pdss-scheduler
systemctl status pdss-web pdss-scheduler --no-pager
hostname -I
```

Access `http://CONTAINER_IP:8080` from the same LAN. The scheduler's local sync root is `/srv/pdss-sync` in the LXC; create subdirectories there with `pdss` ownership before adding jobs in the UI. To expose host files, use a Proxmox LXC bind mount and carefully map UID/GID permissions; do not turn the container privileged just to fix permissions.

To update:
```bash
cd /opt/proton-drive-secure-sync
git pull --ff-only
/opt/proton-drive-secure-sync/.venv/bin/pip install -r requirements-web.txt
systemctl restart pdss-web pdss-scheduler
```

**Important:** HTTP is unencrypted; restrict port 8080 to a trusted LAN or VPN and use HTTPS via reverse proxy for remote access. The Rclone Proton Drive backend is beta; verify the installed Rclone supports `protondrive` and test with disposable data. This installer has not been integration-tested inside a live Proxmox LXC.

# Proton Drive Secure Sync — Web container v0.5 (experimental)

Browser-based manual Rclone file browser and upload/download frontend for Docker. **Not an official Proton app, not audited, and not automatic synchronization.** The previous GTK3 desktop client is still available as `python3 run.py`.

## Docker installation (Ubuntu or other Linux host)

Install Docker Engine and the Docker Compose plugin on the host. Then:

```bash
git clone https://github.com/andreafar1/proton-drive-secure-sync.git
cd proton-drive-secure-sync
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set `PDSS_PASSWORD` in `.env` to a long, unique password and `PDSS_SESSION_SECRET` to a **different** random value from the command above (32+ characters). Never commit `.env`.

Configure a compatible Rclone installation on the **host** using `rclone config` and a test Proton Drive account, then copy its config to `./config/rclone.conf`. Keep this file private and readable by UID 10001 inside the container, e.g.:

```bash
mkdir -p config
sudo install -m 0444 ~/.config/rclone/rclone.conf ./config/rclone.conf
mkdir -p sync\n# Ensure the mounted folder is readable/writable by container UID 10001:\nsudo chown -R 10001:10001 sync\ndocker compose up -d --build
docker compose logs --tail=60
```

**Important:** the Docker image installs the Debian packaged Rclone. Confirm `docker compose exec proton-drive-secure-sync rclone version` and `rclone listremotes` show a version supporting the configured Proton Drive backend. If not, install a compatible trusted Rclone release in a custom image before relying on it. Do not assume every Rclone version supports Proton Drive.

Access from a browser on the same LAN:

```
http://SERVER_IP:8080
```

Replace `SERVER_IP` with the Docker host's actual IP address. Allow TCP 8080 in the host firewall **only from your trusted LAN/VPN**. The Docker Compose file binds port 8080 to all host interfaces. **HTTP is unencrypted**; for access across the internet, do not expose 8080 directly. Put the service behind an HTTPS reverse proxy with access controls or a VPN; set `PDSS_HTTPS=1` when HTTPS is correctly configured. Never port-forward 8080 to the public internet.

## Scheduled one-way copy jobs (v0.5)

The **Sincronizzazione** tab lets you create jobs with a name, direction, local folder relative to `/sync`, remote folder relative to the Rclone remote, and frequency: manual, 15 min, 30 min, 1 hour, 6 hours, 12 hours, or 24 hours.

Jobs start **disabled**. Use **Avvia ora** for a one-time copy, or **Attiva** to schedule recurring runs. A dedicated `scheduler` container handles jobs even after the browser closes. Job configuration, last run, last status and next run are stored in `/data/schedules.sqlite3` on the named Docker volume.

**Local folders must already exist** within the host folder mounted to `/sync`. The default is `./sync` next to `compose.yaml`. To sync a different host directory, add `PDSS_LOCAL_DIR=/absolute/path/to/folder` to `.env`, ensure UID 10001 can read it and (for downloads) write to it, then recreate the containers. Inside the UI, specify a relative path such as `Documents` (or `.` for the mounted root).

Examples:
- `Locale → Proton Drive`, local `Documents`, remote `Backup/Documents`, every 60 minutes: copy new files from `/sync/Documents` into the remote subfolder.
- `Proton Drive → Locale`, local `CloudCopy`, remote `Documents`, every 24 hours: copy new remote files into `/sync/CloudCopy`.

**This is not full sync:** the scheduler uses `rclone copy --ignore-existing`, which skips destination files already present even if their contents changed. It does not delete destination files. The operation is not transactional, and remote concurrent writers or incomplete transfers still require independent testing. There is no bidirectional mode or automatic conflict resolution.

Check status:
```bash
docker compose ps
docker compose logs --tail=50 scheduler
```

## Features

- Responsive purple web UI inspired by the desktop mockup
- Password-protected session (HTTP-only, SameSite Strict cookie)
- List and browse remote folders, sizes and modification times
- Manual upload to **remote root** (100 MB default maximum), manual download from any browsed folder
- Confirmation dialogs; session-only transfer activity and operation log in the browser
- Server-side remote path validation; local staging, no-clobber publication for downloads
- No delete, overwrite command, or bidirectional synchronization; scheduled one-way non-destructive copy jobs are opt-in
- Rclone config mounted read-only; container runs as non-root, drops Linux capabilities, read-only root filesystem

## Limitations and safety

- **Do not use for important files without independent backups.** No real Proton Drive end-to-end integration or security audit has been performed.
- Upload collision preflight and Rclone `--immutable` are not atomic protection against concurrent remote writes.
- SHA-256 checks the local staged file, not the authenticity of the remote file.
- Uploads/downloads are synchronous per HTTP request and may time out on network interruptions. No cancellation or true progress bar yet.
- The browser operation log is not persistent. Scheduled jobs retain only their last result and timestamps; the Transfer tab is a browser session feed, not a transfer progress queue.\n- The scheduler runs one job at a time and may take up to an hour per job. It does not automatically resolve changed files or conflicts.
- Authentication is a single shared password, not a multi-user identity system. There is no rate limiter; restrict access at the reverse proxy/firewall.
- Secrets and Rclone configuration remain on the host. File permissions on the mounted Rclone config must allow container UID 10001 to read it; the sample `0444` is a compatibility choice, not ideal for a shared host. Prefer an ACL or a dedicated service-owned copy with restricted permissions.
- The web application has not yet been exercised inside a live Docker container in this development environment. Test with disposable data first.

## Desktop mode

```bash
sudo apt install python3 python3-gi gir1.2-gtk-3.0 rclone
python3 -m unittest discover -s tests -v
python3 run.py
```

## Local test suite

```bash
python3 -m unittest discover -s tests -v
```

Tests mock Rclone and do not validate a real Proton backend. The web application requires the packages in `requirements-web.txt`.

## Security note

The project is experimental. Do not publish your `.env`, `config/rclone.conf`, passwords, Rclone access tokens, or screenshots containing secrets. Treat your Rclone config as sensitive.
