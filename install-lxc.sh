#!/usr/bin/env bash
# Run as root inside an Ubuntu LXC container with systemd.
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
APP=/opt/proton-drive-secure-sync
CONF=/etc/proton-drive-secure-sync
USER_NAME=pdss
if [[ ${EUID} -ne 0 ]]; then echo "Run with sudo or as root"; exit 1; fi
if [[ ! -d /run/systemd/system ]]; then echo "This container is not running systemd"; exit 1; fi
apt-get update
apt-get install -y git python3 python3-venv python3-pip rclone ca-certificates
if ! id "$USER_NAME" >/dev/null 2>&1; then
    useradd --system --home-dir /var/lib/pdss --create-home --shell /usr/sbin/nologin "$USER_NAME"
fi
if [[ -d "$APP/.git" ]]; then
    git -C "$APP" pull --ff-only
elif [[ ! -e "$APP" ]]; then
    git clone https://github.com/andreafar1/proton-drive-secure-sync.git "$APP"
else
    echo "$APP exists but is not a git checkout; stopping"; exit 1
fi
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install --disable-pip-version-check -r "$APP/requirements-web.txt"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0750 /var/lib/pdss /var/lib/pdss/data /srv/pdss-sync
install -d -o root -g "$USER_NAME" -m 0750 "$CONF"
if [[ ! -f "$CONF/app.env" ]]; then
    SECRET=$("$APP/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))')
    PASS=$("$APP/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(24))')
    cat >"$CONF/app.env" <<EOF
PDSS_REMOTE=proton:
PDSS_PASSWORD=$PASS
PDSS_SESSION_SECRET=$SECRET
PDSS_WORKDIR=/var/lib/pdss/data
PDSS_DB=/var/lib/pdss/data/schedules.sqlite3
PDSS_SYNC_ROOT=/srv/pdss-sync
PDSS_MAX_UPLOAD_MB=100
PDSS_HTTPS=0
RCLONE_CONFIG=$CONF/rclone.conf
EOF
    chown root:"$USER_NAME" "$CONF/app.env"
    chmod 0640 "$CONF/app.env"
    echo
    echo "IMPORTANT: save this generated web password now (shown only once):"
    echo "$PASS"
    echo
else
    echo "Preserving existing $CONF/app.env and password"
fi
if [[ ! -f "$CONF/rclone.conf" ]]; then
    install -o "$USER_NAME" -g "$USER_NAME" -m 0600 /dev/null "$CONF/rclone.conf"
fi
cat >/etc/systemd/system/pdss-web.service <<'EOF'
[Unit]
Description=Proton Drive Secure Sync web UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pdss
Group=pdss
WorkingDirectory=/opt/proton-drive-secure-sync
EnvironmentFile=/etc/proton-drive-secure-sync/app.env
ExecStart=/opt/proton-drive-secure-sync/.venv/bin/gunicorn --workers 2 --threads 2 --timeout 3600 --bind 0.0.0.0:8080 webapp:app
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/pdss/data /srv/pdss-sync
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
cat >/etc/systemd/system/pdss-scheduler.service <<'EOF'
[Unit]
Description=Proton Drive Secure Sync scheduler
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pdss
Group=pdss
WorkingDirectory=/opt/proton-drive-secure-sync
EnvironmentFile=/etc/proton-drive-secure-sync/app.env
ExecStart=/opt/proton-drive-secure-sync/.venv/bin/python scheduler.py
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/pdss/data /srv/pdss-sync
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable pdss-web.service pdss-scheduler.service
echo "Services installed and enabled, but NOT started."
echo "Next: configure Rclone for pdss user:"
echo "  sudo -u pdss env RCLONE_CONFIG=$CONF/rclone.conf rclone config"
echo "Then test remote and start:"
echo "  sudo -u pdss env RCLONE_CONFIG=$CONF/rclone.conf rclone lsd proton:"
echo "  systemctl start pdss-web pdss-scheduler"
echo "  hostname -I"
