# Proton Drive Secure Sync — Web container v0.4 (experimental)

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
docker compose up -d --build
docker compose logs --tail=60
```

**Important:** the Docker image installs the Debian packaged Rclone. Confirm `docker compose exec proton-drive-secure-sync rclone version` and `rclone listremotes` show a version supporting the configured Proton Drive backend. If not, install a compatible trusted Rclone release in a custom image before relying on it. Do not assume every Rclone version supports Proton Drive.

Access from a browser on the same LAN:

```
http://SERVER_IP:8080
```

Replace `SERVER_IP` with the Docker host's actual IP address. Allow TCP 8080 in the host firewall **only from your trusted LAN/VPN**. The Docker Compose file binds port 8080 to all host interfaces. **HTTP is unencrypted**; for access across the internet, do not expose 8080 directly. Put the service behind an HTTPS reverse proxy with access controls or a VPN; set `PDSS_HTTPS=1` when HTTPS is correctly configured. Never port-forward 8080 to the public internet.

## Features

- Responsive purple web UI inspired by the desktop mockup
- Password-protected session (HTTP-only, SameSite Strict cookie)
- List and browse remote folders, sizes and modification times
- Manual upload to **remote root** (100 MB default maximum), manual download from any browsed folder
- Confirmation dialogs; session-only transfer activity and operation log in the browser
- Server-side remote path validation; local staging, no-clobber publication for downloads
- No delete, overwrite command, scheduled synchronization, or automatic background operations
- Rclone config mounted read-only; container runs as non-root, drops Linux capabilities, read-only root filesystem

## Limitations and safety

- **Do not use for important files without independent backups.** No real Proton Drive end-to-end integration or security audit has been performed.
- Upload collision preflight and Rclone `--immutable` are not atomic protection against concurrent remote writes.
- SHA-256 checks the local staged file, not the authenticity of the remote file.
- Uploads/downloads are synchronous per HTTP request and may time out on network interruptions. No cancellation or true progress bar yet.
- The operation log is not persistent. The Transfer tab is a session activity feed, not a queue.
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
