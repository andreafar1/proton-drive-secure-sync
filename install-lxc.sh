#!/usr/bin/env bash
# Run as root inside an Ubuntu LXC container with systemd.
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
APP=/opt/proton-drive-secure-sync
CONF=/etc/proton-drive-secure-sync
USER_NAME=pdss
if [[ ${EUID} -ne 0 ]]; then echo "Run with sudo or as root"; exit 1; fi
if [[ ! -d /run/systemd/system ]]; then echo "This container is not running systemd"; exit 1; fi
echo "=== Installazione guidata Proton Drive Secure Sync (LXC Ubuntu) ==="
read -r -p "Porta web [8080]: " PDSS_PORT
PDSS_PORT=${PDSS_PORT:-8080}
[[ $PDSS_PORT =~ ^[0-9]+$ ]] && (( PDSS_PORT>=1024 && PDSS_PORT<=65535 )) || { echo "Porta non valida"; exit 1; }
read -r -p "Nome remoto Rclone [proton]: " PDSS_NAME
PDSS_NAME=${PDSS_NAME:-proton}
[[ $PDSS_NAME =~ ^[a-zA-Z][a-zA-Z0-9_-]{0,50}$ ]] || { echo "Nome remoto non valido"; exit 1; }
read -r -p "Cartella locale da sincronizzare [/srv/pdss-sync]: " PDSS_LOCAL
PDSS_LOCAL=${PDSS_LOCAL:-/srv/pdss-sync}
[[ $PDSS_LOCAL == /* && $PDSS_LOCAL != *" "* && $PDSS_LOCAL != *".."* && $PDSS_LOCAL != *"="* && $PDSS_LOCAL != *"'"* && $PDSS_LOCAL != *'"'* ]] || { echo "Cartella locale non valida"; exit 1; }
[[ $PDSS_LOCAL != / && $PDSS_LOCAL != /etc && $PDSS_LOCAL != /root && $PDSS_LOCAL != /var && $PDSS_LOCAL != /opt ]] || { echo "Cartella troppo ampia"; exit 1; }
echo
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
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0750 /var/lib/pdss /var/lib/pdss/data "$PDSS_LOCAL"
install -d -o root -g "$USER_NAME" -m 0750 "$CONF"
if [[ ! -f "$CONF/app.env" ]]; then
    SECRET=$("$APP/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))')
    read -r -s -p "Scegli password web (minimo 16 caratteri): " PASS
    echo
    [[ ${#PASS} -ge 16 && "$PASS" != *" "* && "$PASS" != *"="* && "$PASS" != *"'"* && "$PASS" != *'"'* && "$PASS" != *'
    cat >"$CONF/app.env" <<EOF
PDSS_REMOTE=$PDSS_NAME:
PDSS_PASSWORD=$PASS
PDSS_SESSION_SECRET=$SECRET
PDSS_PORT=$PDSS_PORT
PDSS_WORKDIR=/var/lib/pdss/data
PDSS_DB=/var/lib/pdss/data/schedules.sqlite3
PDSS_SYNC_ROOT=$PDSS_LOCAL
PDSS_MAX_UPLOAD_MB=100
PDSS_HTTPS=0
RCLONE_CONFIG=$CONF/rclone.conf
EOF
    chown root:"$USER_NAME" "$CONF/app.env"
    chmod 0640 "$CONF/app.env"
    echo
    echo "Password web impostata (non mostrata). Conservala."
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
ExecStart=/bin/sh -c 'exec /opt/proton-drive-secure-sync/.venv/bin/gunicorn --workers 2 --threads 2 --timeout 3600 --bind "0.0.0.0:$PDSS_PORT" webapp:app'
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/pdss/data $PDSS_LOCAL
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
cat >/etc/systemd/system/pdss-scheduler.service <<EOF
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
echo "Servizi installati. Configura Rclone ora (tipo protondrive, nome $PDSS_NAME)."
read -r -p "Avviare la configurazione guidata Rclone? [S/n]: " ANSWER
if [[ $ANSWER != n && $ANSWER != N ]]; then
    runuser -u pdss -- env RCLONE_CONFIG="$CONF/rclone.conf" rclone config
fi
if runuser -u pdss -- env RCLONE_CONFIG="$CONF/rclone.conf" rclone lsd "$PDSS_NAME:" >/dev/null; then
    systemctl restart pdss-web pdss-scheduler
    echo "Installazione completata. Apri http://IP_DEL_CONTAINER:$PDSS_PORT"
    echo "IP rilevato: $(hostname -I)"
else
    echo "Remoto non verificato: servizi abilitati, non avviati automaticamente ora."
    echo "Riconfigura Rclone e poi esegui: systemctl start pdss-web pdss-scheduler"
fi
echo "Next: configure Rclone for pdss user:"
echo "  sudo -u pdss env RCLONE_CONFIG=$CONF/rclone.conf rclone config"
echo "Then test remote and start:"
echo "  sudo -u pdss env RCLONE_CONFIG=$CONF/rclone.conf rclone lsd proton:"
echo "  systemctl start pdss-web pdss-scheduler"
echo "  hostname -I"
* ]] || { echo "Password non valida"; exit 1; }
    read -r -s -p "Conferma password web: " CONFIRM
    echo
    [[ "$PASS" == "$CONFIRM" ]] || { echo "Password non coincidente"; exit 1; }
    unset CONFIRM
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
