# Proton Drive Secure Sync

Interfaccia web sperimentale per consultare Proton Drive tramite Rclone, trasferire file manualmente e programmare copie unidirezionali **senza cancellazioni automatiche**.

> **Attenzione:** progetto non ufficiale Proton, non sottoposto ad audit e non ancora collaudato end-to-end su un account Proton Drive reale. Prima prova con file sacrificabili e conserva sempre un backup indipendente. Non esporre la porta 8080 direttamente a Internet.

## Installazione su Ubuntu LXC in Proxmox (consigliata)

Questa installazione funziona **dentro un container Ubuntu LXC già esistente**, senza Docker. Richiede systemd, accesso root nel container, rete funzionante e una versione di Rclone compatibile con il backend Proton Drive.

### 1. Apri la console del container

Dalla GUI di Proxmox: seleziona il container Ubuntu → **Console**. In alternativa, sul nodo Proxmox:

```bash
pct enter ID_CONTAINER
```

I comandi successivi si eseguono **dentro il container, come root**.

### 2. Scarica il progetto e installalo

```bash
apt update
apt install -y git
git clone https://github.com/andreafar1/proton-drive-secure-sync.git /tmp/pdss-installer
cd /tmp/pdss-installer
less install-lxc.sh
bash install-lxc.sh
```

Lo script:
- installa Python, ambiente virtuale, dipendenze web e Rclone;
- scarica il progetto in `/opt/proton-drive-secure-sync`;
- crea l'utente non privilegiato `pdss`;
- prepara `/var/lib/pdss/data` e `/srv/pdss-sync`;
- genera una password web e una chiave di sessione;
- crea e **abilita all'avvio** i servizi `pdss-web` e `pdss-scheduler`.

**Salva subito la password mostrata a video:** l'installer la visualizza una sola volta. I servizi non vengono avviati prima della configurazione di Rclone.

### 3. Configura Rclone per Proton Drive

Controlla innanzitutto la versione e la disponibilità del backend:

```bash
rclone version
rclone config providers | grep -i proton
```

Se `protondrive` non è disponibile, aggiorna Rclone da una fonte ufficiale verificata prima di proseguire. Il backend Proton Drive può avere limitazioni e comportamenti sperimentali.

Configura il remoto **con il nome `proton`** (che nell'app appare come `proton:`):

```bash
runuser -u pdss -- env RCLONE_CONFIG=/etc/proton-drive-secure-sync/rclone.conf rclone config
```

Verifica il collegamento:

```bash
runuser -u pdss -- env RCLONE_CONFIG=/etc/proton-drive-secure-sync/rclone.conf rclone lsd proton:
```

Se non funziona, **non abilitare ancora le attività programmate**. Il file `/etc/proton-drive-secure-sync/rclone.conf` contiene credenziali sensibili: non pubblicarlo né inviarlo ad altri.

### 4. Avvia i servizi automaticamente

```bash
systemctl start pdss-web pdss-scheduler
systemctl status pdss-web pdss-scheduler --no-pager
systemctl is-enabled pdss-web pdss-scheduler
```

Per consultare eventuali errori:

```bash
journalctl -u pdss-web -u pdss-scheduler -n 80 --no-pager
```

I servizi sono abilitati al riavvio automatico del container.

### 5. Accedi alla pagina dall'indirizzo IP

Visualizza l'IP del container:

```bash
hostname -I
```

Da un dispositivo nella stessa LAN, apri:

```text
http://IP_DEL_CONTAINER:8080
```

Esempio puramente illustrativo: `http://192.168.1.150:8080`. Accedi con la password generata al punto 2. Se non risponde, controlla `systemctl status pdss-web`, l'indirizzo IP, il firewall del container e quello di Proxmox.

**Sicurezza:** HTTP non cifra le credenziali. Usa soltanto una LAN fidata o una VPN; per accesso remoto predisponi un reverse proxy HTTPS con controllo degli accessi. Non fare port forwarding pubblico della porta 8080.

### 6. Scegli le cartelle da copiare e la frequenza

La cartella locale esposta all'applicazione è:

```text
/srv/pdss-sync
```

Crea, ad esempio:

```bash
install -d -o pdss -g pdss /srv/pdss-sync/Documenti
```

Nella pagina web apri **Sincronizzazione** → crea una nuova attività. Esempio:

| Campo | Valore |
| --- | --- |
| Nome | Backup Documenti |
| Direzione | Locale → Proton Drive |
| Cartella locale | `Documenti` |
| Cartella remota | `Backup/Documenti` |
| Frequenza | Ogni 60 minuti |

Le attività nascono **disattivate**. Puoi premere **Avvia ora** per una copia manuale, oppure **Attiva** per programmare le esecuzioni. Le opzioni disponibili sono: manuale, ogni 15 o 30 minuti, ogni 1, 6, 12 o 24 ore.

Il pianificatore gira come servizio systemd anche quando chiudi il browser. Conserva attività, ultimo esito e prossima esecuzione nel database SQLite `/var/lib/pdss/data/schedules.sqlite3`.

**Limite importante:** usa `rclone copy --ignore-existing`. Copia file nuovi, ma **non aggiorna** quelli già presenti nella destinazione, anche se modificati. Non è una sincronizzazione bidirezionale; non cancella file, non risolve conflitti e non garantisce atomicità in presenza di scritture concorrenti.

Per esporre una cartella del nodo Proxmox al container LXC, usa un bind mount configurato su Proxmox e verifica attentamente i permessi UID/GID; non rendere il container privilegiato solo per aggirare i permessi.

### Aggiornare l'applicazione da GitHub

Dentro il container, come root:

```bash
cd /opt/proton-drive-secure-sync
git pull --ff-only
/opt/proton-drive-secure-sync/.venv/bin/pip install -r requirements-web.txt
systemctl restart pdss-web pdss-scheduler
```

### Comandi utili

```bash
systemctl status pdss-web pdss-scheduler --no-pager
journalctl -u pdss-web -f
journalctl -u pdss-scheduler -f
systemctl restart pdss-web pdss-scheduler
```

## Installazione alternativa con Docker Compose

Se invece usi Docker (non necessario su Proxmox LXC), sono disponibili `Dockerfile` e `compose.yaml`.

```bash
git clone https://github.com/andreafar1/proton-drive-secure-sync.git
cd proton-drive-secure-sync
cp .env.example .env
mkdir -p config sync
```

Imposta password e segreto distinti in `.env`, configura un remoto Rclone compatibile e prepara `config/rclone.conf` con permessi che consentano la lettura all'UID 10001 del container. Poi:

```bash
sudo chown -R 10001:10001 sync
docker compose up -d --build
docker compose ps
```

L'interfaccia sarà raggiungibile su `http://IP_SERVER:8080` **solo dalla rete fidata**. Il container scheduler esegue le attività programmate; la directory locale è montata in `/sync`. Per cambiare la directory host, imposta `PDSS_LOCAL_DIR` in `.env`.

## Funzionalità e limitazioni

- Interfaccia web responsive con esplorazione delle cartelle remote.
- Upload e download manuali con conferma; upload manuale nella radice remota.
- Pianificazione di copie unidirezionali con frequenze configurabili.
- Nessuna cancellazione automatica, nessuna sovrascrittura intenzionale.
- Accesso con password condivisa; nessun sistema multiutente o rate limiting applicativo.
- Registro browser temporaneo; per le attività pianificate sono memorizzati solo l'ultimo stato e i tempi.
- Nessuna barra di progresso reale o cancellazione dei trasferimenti.
- Verifica SHA-256 locale non equivalente a verifica crittografica del contenuto remoto.
- Test unitari con Rclone simulato, non una prova di sicurezza o affidabilità end-to-end.

## Test e modalità desktop precedente

```bash
cd /opt/proton-drive-secure-sync
/opt/proton-drive-secure-sync/.venv/bin/python -m unittest discover -s tests -v
```

La precedente GUI GTK3 rimane nel repository (`run.py`), ma per Ubuntu LXC senza desktop si raccomanda l'interfaccia web.

## Licenza e contributi

Prima di distribuire o riutilizzare il progetto, verificare la presenza di una licenza esplicita nel repository. Segnalazioni di bug e test con dati non sensibili sono benvenuti.
