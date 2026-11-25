#!/usr/bin/env bash
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
APP=/opt/proton-drive-secure-sync
CONF=/etc/proton-drive-secure-sync
[[ $EUID -eq 0 ]] || { echo "Esegui con sudo su Linux (LXC o Raspberry Pi)"; exit 1; }
[[ -d /run/systemd/system ]] || { echo "systemd non disponibile"; exit 1; }
echo "=== Installazione guidata Proton Drive Secure Sync ==="
read -r -p "Porta web [8080]: " PORT
PORT=${PORT:-8080}
[[ $PORT =~ ^[0-9]+$ ]] && (( PORT>=1024 && PORT<=65535 )) || { echo "Porta non valida"; exit 1; }
read -r -p "Nome remoto Rclone [proton]: " REMOTE
REMOTE=${REMOTE:-proton}
[[ $REMOTE =~ ^[a-zA-Z][a-zA-Z0-9_-]{0,50}$ ]] || { echo "Remoto non valido"; exit 1; }
read -r -p "Cartella locale [/srv/pdss-sync]: " SYNC
SYNC=${SYNC:-/srv/pdss-sync}
[[ $SYNC == /* && $SYNC != *" "* && $SYNC != *".."* && $SYNC != *"="* && $SYNC != *"'"* && $SYNC != *'"'* ]] || { echo "Percorso non valido"; exit 1; }
[[ $SYNC != / && $SYNC != /etc && $SYNC != /root && $SYNC != /var && $SYNC != /opt ]] || { echo "Cartella troppo ampia"; exit 1; }
apt-get update
apt-get install -y git python3 python3-venv python3-pip rclone ca-certificates curl unzip
if ! rclone config providers | grep '"Name": "protondrive"' >/dev/null; then
  echo "Rclone con supporto Proton Drive necessario: installazione ufficiale."
  TMP_INSTALL=$(mktemp)
  curl --fail --silent --show-error --location https://rclone.org/install.sh -o "$TMP_INSTALL"
  bash "$TMP_INSTALL"
  rm -f "$TMP_INSTALL"
  hash -r
fi
if ! rclone config providers | grep '"Name": "protondrive"' >/dev/null; then
  echo "Backend Proton Drive non disponibile"; exit 1
fi
id pdss >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/pdss --shell /usr/sbin/nologin pdss
if [[ -d "$APP/.git" ]]; then
  git -C "$APP" pull --ff-only
elif [[ ! -e "$APP" ]]; then
  git clone https://github.com/andreafar1/proton-drive-secure-sync.git "$APP"
else
  echo "Directory applicazione occupata da altri file"; exit 1
fi
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -r "$APP/requirements-web.txt"
install -d -o pdss -g pdss -m 0750 /var/lib/pdss/data
install -d -o pdss -g pdss -m 0700 "$CONF"
chown pdss:pdss "$CONF"
if [[ ! -e "$SYNC" ]]; then
  install -d -o pdss -g pdss -m 0750 "$SYNC"
else
  [[ -d "$SYNC" && ! -L "$SYNC" ]] || { echo "Cartella locale non valida"; exit 1; }
  echo "Cartella esistente: permessi conservati, verifica accesso utente pdss."
fi
if [[ -f "$CONF/app.env" ]]; then
  PASS=$(sed -n 's/^PDSS_PASSWORD=//p' "$CONF/app.env" | head -1)
  SECRET=$(sed -n 's/^PDSS_SESSION_SECRET=//p' "$CONF/app.env" | head -1)
else
  PASS=""
  SECRET=""
fi
if [[ -n "$PASS" && -n "$SECRET" ]]; then
  echo "Password precedente conservata."
else
  read -r -s -p "Password web (minimo 16 caratteri): " PASS
  echo
  [[ ${#PASS} -ge 16 && "$PASS" != *" "* && "$PASS" != *"="* && "$PASS" != *"'"* && "$PASS" != *'"'* && "$PASS" != *'$'* && "$PASS" != *'\'* ]] || { echo "Password non valida"; exit 1; }
  read -r -s -p "Ripeti password: " CONFIRM
  echo
  [[ $PASS == "$CONFIRM" ]] || { echo "Password diverse"; exit 1; }
  SECRET=$("$APP/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))')
fi
cat >"$CONF/app.env" <<EOF
PDSS_REMOTE=$REMOTE:
PDSS_PASSWORD=$PASS
PDSS_SESSION_SECRET=$SECRET
PDSS_PORT=$PORT
PDSS_WORKDIR=/var/lib/pdss/data
PDSS_DB=/var/lib/pdss/data/schedules.sqlite3
PDSS_SYNC_ROOT=$SYNC
PDSS_MAX_UPLOAD_MB=100
PDSS_HTTPS=0
XDG_CACHE_HOME=/var/lib/pdss/data/cache
RCLONE_CONFIG=$CONF/rclone.conf
EOF
chown root:pdss "$CONF/app.env"
chmod 0640 "$CONF/app.env"
unset PASS SECRET CONFIRM
if [[ ! -f "$CONF/rclone.conf" ]]; then
  install -o pdss -g pdss -m 0600 /dev/null "$CONF/rclone.conf"
fi
cat >/etc/systemd/system/pdss-web.service <<'EOF'
[Unit]
Description=Proton Drive Secure Sync Web
After=network-online.target
Wants=network-online.target
[Service]
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
ReadWritePaths=/var/lib/pdss/data /etc/proton-drive-secure-sync
PrivateTmp=true
[Install]
WantedBy=multi-user.target
EOF
cat >/etc/systemd/system/pdss-scheduler.service <<EOF
[Unit]
Description=Proton Drive Secure Sync Scheduler
After=network-online.target
Wants=network-online.target
[Service]
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
ReadWritePaths=/var/lib/pdss/data /etc/proton-drive-secure-sync $SYNC
PrivateTmp=true
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable pdss-web pdss-scheduler
echo "Il cloud si collega dalla GUI: Impostazioni -> Collega Proton Drive."
systemctl restart pdss-web pdss-scheduler
echo "Installazione completata! Apri http://IP_DEL_SERVER:$PORT"
echo "IP del server: $(hostname -I)"
echo "Accedi e collega il cloud dalla sezione Impostazioni."
echo "Non esporre HTTP a Internet: usa LAN fidata o VPN/HTTPS."
