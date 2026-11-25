# Proton Drive Secure Sync — Web v0.7

**Installazione:** [Raspberry Pi](#installazione-su-raspberry-pi) · [Proxmox LXC](#installazione-su-ubuntu-lxc-in-proxmox-consigliata) · [Docker](#installazione-alternativa-con-docker-compose)

Interfaccia web sperimentale per consultare Proton Drive tramite Rclone, trasferire file manualmente e programmare copie unidirezionali **senza cancellazioni automatiche**.

> **Attenzione:** progetto non ufficiale Proton, non sottoposto ad audit e non completamente collaudato end-to-end; la compatibilità Raspberry Pi non è ancora verificata su hardware reale. Prima prova con file sacrificabili e conserva sempre un backup indipendente. Non esporre la porta 8089 direttamente a Internet.


## Installazione su Raspberry Pi

### 1. Preparazione

Consigliato Raspberry Pi 4 o 5, Raspberry Pi OS Lite **64 bit**, alimentatore adeguato, connessione di rete e microSD o SSD. Docker non è necessario. Con Raspberry Pi Imager scegli Raspberry Pi OS Lite (64-bit), configura nome host, utente, rete e SSH, quindi avvia il dispositivo. Collegati via SSH con il nome utente e l'indirizzo IP scelti.

### 2. Installazione guidata

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/andreafar1/proton-drive-secure-sync.git
cd proton-drive-secure-sync
sudo bash install-lxc.sh
```

Il nome dello script è storico: lo stesso installer serve Raspberry Pi e Ubuntu LXC. Installa Python, Rclone e i servizi systemd; se manca il backend Proton Drive, scarica ed esegue lo script ufficiale Rclone con privilegi root. Verifica la provenienza del codice prima di eseguirlo.

| Impostazione | Valore consigliato |
| --- | --- |
| Porta web | 8089 |
| Remoto Rclone | proton |
| Cartella locale predefinita | /srv/pdss-sync |
| Password web | Almeno 16 caratteri, distinta da Proton |

### 3. Disco USB o SSD (facoltativo)

Identifica il disco senza formattarlo:

```bash
lsblk -f
```

Configura un montaggio persistente tramite UUID in /etc/fstab, ad esempio in /mnt/ssd, secondo il filesystem effettivo. Prima di creare la directory di backup verifica il montaggio:

```bash
findmnt --mountpoint /mnt/ssd
```

Solo se il disco risulta montato, puoi creare una nuova directory dedicata (dopo l'installazione, quando esiste l'utente pdss):

```bash
sudo install -d -o pdss -g pdss -m 0750 /mnt/ssd/proton-sync
sudo -u pdss test -r /mnt/ssd/proton-sync
sudo -u pdss test -w /mnt/ssd/proton-sync
```

Per directory esistenti, conserva proprietari e permessi; concedi soltanto l'accesso necessario a pdss, ad esempio tramite ACL dove supportate. Non usare chmod 777. Per il backup verso Proton occorrono lettura dei file e attraversamento delle directory; per il ripristino locale occorre anche scrittura. Il selettore non mostra directory inaccessibili.

**Importante:** non è ancora presente un controllo automatico del montaggio del disco. Verifica il montaggio dopo ogni riavvio e disattiva le attività prima di scollegare il disco. In caso contrario una copia verso locale potrebbe finire sulla microSD.

### 4. Accesso e collegamento Proton

```bash
hostname -I
sudo systemctl status pdss-web pdss-scheduler --no-pager
rclone version
```

Apri dal PC o smartphone nella LAN fidata http://IP_DEL_RASPBERRY:8089 (o la porta scelta). Accedi con la password web, apri Impostazioni e collega Proton con email, password e codice 2FA se richiesto. Non disabilitare il 2FA. Apri File remoti e premi Aggiorna per consultare il cloud. Non esporre HTTP a Internet; usa VPN o HTTPS.

### 5. Primo backup dalla GUI

1. Apri Sincronizzazione e assegna un nome all'attività.
2. Scegli Locale → Proton Drive.
3. Premi Sfoglia accanto a Cartella sul server, entra in mnt → ssd → proton-sync e seleziona la cartella.
4. Scegli la destinazione Proton tramite Sfoglia oppure digita un percorso relativo, ad esempio Backup/Raspberry.
5. Seleziona la frequenza e premi Crea attività.
6. Premi Avvia ora per provare con pochi file non importanti; verifica i risultati e la cronologia. Solo dopo premi Attiva per programmare le copie.

Le attività continuano anche a browser chiuso. La copia non elimina file e non aggiorna file già presenti: non è un backup versionato né una sincronizzazione bidirezionale.

### 6. Aggiornamento e diagnosi

```bash
cd /opt/proton-drive-secure-sync
sudo git pull --ff-only
sudo /opt/proton-drive-secure-sync/.venv/bin/pip install -r requirements-web.txt
sudo systemctl restart pdss-web pdss-scheduler
```

Attendi la conclusione delle copie prima di riavviare. Se cambiano le unità systemd, riesegui l'installer con le impostazioni precedenti. Premi Ctrl+F5 nel browser.

```bash
sudo journalctl -u pdss-web -n 50 --no-pager
sudo journalctl -u pdss-scheduler -n 50 --no-pager
sudo systemctl is-enabled pdss-web pdss-scheduler
```

Non condividere credenziali, token o codici 2FA. La procedura è prevista per ARM64 ma non ancora collaudata su Raspberry Pi fisico.

## Installazione su Ubuntu LXC in Proxmox (consigliata)

**Installazione rapida:** bastano `git clone`, `cd` e `bash install-lxc.sh`: durante la procedura scegli porta, password web e cartella; colleghi Proton Drive successivamente dalla GUI. Non è necessario Docker.

Questa installazione funziona **dentro un container Ubuntu LXC già esistente**, senza Docker. Richiede systemd, accesso root nel container, rete funzionante e una versione di Rclone compatibile con il backend Proton Drive.

### 1. Apri la console del container

Dalla GUI di Proxmox: seleziona il container Ubuntu → **Console**. In alternativa, sul nodo Proxmox:

```bash
pct enter ID_CONTAINER
```

I comandi successivi si eseguono **dentro il container, come root**.

### 2. Scarica da GitHub e avvia l'installazione guidata

Dentro il container Ubuntu, come root:

```bash
apt update && apt install -y git
git clone https://github.com/andreafar1/proton-drive-secure-sync.git
cd proton-drive-secure-sync
bash install-lxc.sh
```

L'installer chiede **porta web** (8089), **nome del remoto Rclone** (`proton`), **cartella locale** (`/srv/pdss-sync`) e **password web** (almeno 16 caratteri). Scarica e aggiorna il progetto in `/opt/proton-drive-secure-sync`, prepara Python e abilita e avvia i servizi systemd. **Non devi inserire le credenziali Proton durante l'installazione.**

Apri quindi `http://IP_DEL_CONTAINER:8089` (o la porta scelta), accedi con la password web e vai in **Impostazioni → Collega Proton Drive**. Inserisci nome utente/email Proton, password Proton e, se richiesto, il codice 2FA. Premi **Collega o sostituisci account**. L'app prepara una configurazione Rclone temporanea e la salva solo dopo un test di connessione riuscito. Il browser non conserva la password nel modulo dopo la richiesta.

**Limiti:** serve una versione di Rclone compatibile con il backend `protondrive`, che è sperimentale. Alcuni account o flussi di autenticazione potrebbero richiedere una configurazione Rclone interattiva da terminale. La password Proton viene protetta con l'oscuramento di Rclone nel file locale: **l'oscuramento non è crittografia forte**; proteggi il container, il file di configurazione e i backup. Non utilizzare questa pagina su HTTP attraverso reti non fidate: usa HTTPS o una VPN.

### Gestione account Proton Drive dalla GUI

**Notifiche ripetute di nuovo accesso Proton:** nelle versioni precedenti la GUI eseguiva controlli Rclone automatici aprendo Impostazioni e caricando i file all'avvio. Ora queste richieste automatiche sono state rimosse. Le operazioni esplicite di verifica, caricamento, download o sincronizzazione continuano a contattare Proton e potrebbero comunque generare notifiche; non è garantito che Rclone riutilizzi sempre la sessione.

In **Impostazioni → Collega Proton Drive** puoi:

- **Vedere lo stato**: `Non collegato`, `Connesso`, `Configurato, ma non raggiungibile` oppure timeout.
- Premere **Verifica connessione** solo quando necessario: il controllo contatta Proton Drive e può provocare una notifica di nuovo accesso (fino a 25 secondi). La visualizzazione dello stato in Impostazioni legge solo la configurazione locale e non contatta Proton.
- **Sostituire l'account** inserendo nuove credenziali e premendo **Collega o sostituisci account**. La vecchia configurazione viene sostituita solo dopo una verifica riuscita.
- **Rimuovere l'account** con conferma: viene eliminata esclusivamente la sezione del remoto Proton nel file Rclone locale. I file su Proton Drive non vengono cancellati.

**Sicurezza durante il cambio account:** tutte le attività programmate vengono disattivate prima della sostituzione o rimozione. Non è consentito cambiare account mentre un'attività risulta in esecuzione. Dopo aver collegato il nuovo account, controlla le cartelle remote e riattiva manualmente solo le attività appropriate. Se la verifica del nuovo account fallisce, la configurazione precedente rimane, ma le attività restano disattivate.

Lo stato `Configurato (non verificato)` indica soltanto che il remoto è presente nel file locale. Lo stato `Connesso` indica che il controllo Rclone è riuscito in quel momento, non garantisce disponibilità continua. La rimozione locale non revoca sessioni o dispositivi dall'account Proton.

### 3. Controlla i servizi

```bash
systemctl status pdss-web pdss-scheduler --no-pager
hostname -I
```

Se il collegamento dalla GUI non funziona, puoi utilizzare la configurazione Rclone da terminale (qui si assume il remoto predefinito `proton`):

```bash
runuser -u pdss -- env RCLONE_CONFIG=/etc/proton-drive-secure-sync/rclone.conf rclone config
runuser -u pdss -- env RCLONE_CONFIG=/etc/proton-drive-secure-sync/rclone.conf rclone lsd proton:
systemctl start pdss-web pdss-scheduler
```

Se hai scelto un nome remoto diverso da `proton`, sostituisci `proton:` nel comando di verifica.

### 4. Avvio automatico

I servizi `pdss-web` e `pdss-scheduler` sono abilitati con systemd: si avviano automaticamente al riavvio del container dopo una corretta configurazione.

### 5. Accedi alla pagina dall'indirizzo IP

Visualizza l'IP del container:

```bash
hostname -I
```

Da un dispositivo nella stessa LAN, apri:

```text
http://IP_DEL_CONTAINER:8089
```

Esempio puramente illustrativo: `http://192.168.1.150:8089` (o la porta scelta durante l’installazione). Accedi con la password scelta durante l'installazione (punto 2), poi apri **Impostazioni** per collegare il cloud. Se non risponde, controlla `systemctl status pdss-web`, l'indirizzo IP, il firewall del container e quello di Proxmox.

**Sicurezza:** HTTP non cifra le credenziali. Usa soltanto una LAN fidata o una VPN; per accesso remoto predisponi un reverse proxy HTTPS con controllo degli accessi. Non fare port forwarding pubblico della porta 8089.

### 6. Scegli le cartelle da copiare e la frequenza

La cartella locale predefinita per i percorsi relativi e il pannello File remoti è:

```text
/srv/pdss-sync
```

Se hai scelto un percorso diverso durante l'installazione, usa quello al posto di `/srv/pdss-sync`.

Crea, ad esempio:

```bash
install -d -o pdss -g pdss /srv/pdss-sync/Documenti
```

Nella pagina web apri **Sincronizzazione → Nuova attività di backup**. Premi **Sfoglia** accanto a **Cartella sul server** per navigare nelle aree `/home`, `/media`, `/mnt` e `/srv` accessibili all'utente `pdss`. Seleziona la directory nella finestra separata. Premi **Sfoglia** accanto a **Cartella Proton Drive** per scegliere la destinazione. I percorsi relativi precedenti restano compatibili. Esempio:

| Campo | Valore |
| --- | --- |
| Nome | Backup Documenti |
| Direzione | Locale → Proton Drive |
| Cartella sul server | `/srv/pdss-sync/Documenti` |
| Cartella remota | `Backup/Documenti` |
| Frequenza | Ogni 60 minuti |

Le attività nascono **disattivate**. Puoi premere **Avvia ora** per una copia manuale, oppure **Attiva** per programmare le esecuzioni. Le opzioni disponibili sono: manuale, ogni 15 o 30 minuti, ogni 1, 6, 12 o 24 ore.

Il pianificatore gira come servizio systemd anche quando chiudi il browser. Conserva attività, cronologia delle esecuzioni concluse, ultimo esito e prossima esecuzione nel database SQLite `/var/lib/pdss/data/schedules.sqlite3`.

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

Se l'aggiornamento modifica le unità systemd, esegui anche `sudo bash install-lxc.sh` mantenendo le impostazioni precedenti. L'installer riscrive app.env e le unità: eventuali personalizzazioni vanno conservate separatamente. Aggiorna il browser con Ctrl+F5.

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

L'interfaccia sarà raggiungibile su `http://IP_SERVER:8089` **solo dalla rete fidata**. Il container scheduler esegue le attività programmate; la directory locale è montata in `/sync`. Per cambiare la directory host, imposta `PDSS_LOCAL_DIR` in `.env`.

## Funzionalità e limitazioni

- Interfaccia web responsive con esplorazione delle cartelle remote.
- Upload e download manuali con conferma; upload manuale nella radice remota.
- Pianificazione di copie unidirezionali con frequenze configurabili.
- Nessuna cancellazione automatica, nessuna sovrascrittura intenzionale.
- Accesso con password condivisa; nessun sistema multiutente o rate limiting applicativo.
- Registro browser temporaneo; cronologia SQLite persistente delle sincronizzazioni concluse (ultime 200 mostrate).
- Dashboard con stato locale della configurazione, prossima attività e lettura manuale dello spazio cloud se supportata da Rclone.
- File manager a due pannelli, albero delle cartelle visitate, ricerca nella cartella corrente e caricamento su richiesta.
- Selettore grafico delle cartelle del server con finestra separata, icone vettoriali e layout responsive.
- Indicatore di attività dei trasferimenti manuali, senza percentuale reale o annullamento.
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
