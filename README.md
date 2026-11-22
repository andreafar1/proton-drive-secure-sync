# Proton Drive Secure Sync v0.3 — experimental

A GTK3 Ubuntu GUI for **manual** uploads/downloads through a separately configured Rclone remote. This is not an official Proton app, not an audited security product, and **not an automatic synchronizer**. Do not use it as the only copy of valuable data.

## Ubuntu setup

```bash
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-3.0 rclone
rclone version
rclone config
python3 -m unittest discover -s tests -v
python3 run.py
```

Run the last two commands from this directory, **without sudo**. Configure a Proton-compatible remote in Rclone (if supported by your installed Rclone build). Enter the remote name, e.g. `proton:`, in the GUI. Rclone owns credentials and encryption/backend handling; this application does not request your password. Do not run untrusted scripts or install unverified Rclone binaries to obtain Proton support.

## Capabilities

- Browse remote folders with a purple-accented GTK3 sidebar, breadcrumb and parent-folder navigation.\n- List remote files and folders with size and modification time.\n- View a session-only operation log, transfer activity, and safety information.\n- Manually upload files to the **remote root only** or download selected files from any browsed folder, with confirmation dialogs.\n- The Transfer and Log tabs share the session log; Settings currently displays information rather than providing a separate settings panel.\n- No cancellation, progress percentage, or persistent operation history yet.
- No delete, sync, move, rename or overwrite command.
- Download into a private staging directory; compute a local SHA-256 and check for changes during staging; publish via an atomic **no-clobber hard link** to the destination directory.
- Open destination directory with `O_NOFOLLOW`; refuse existing filenames and symlink directory destinations; remove incomplete staging data on ordinary failures.
- Upload preflight refuses an existing remote path and invokes Rclone `copyto --immutable`. This is **not** an atomic guarantee against concurrent remote writes.
- No root privileges, shell command interpretation, built-in credentials store or telemetry.

## Security limitations

1. **Not audited or tested against live Proton Drive.** Rclone Proton backend behavior, `--immutable` semantics, and credentials must be validated independently.
2. SHA-256 verifies that the staged local file remains stable while checking it; it **does not** authenticate remote content or compare with a trusted remote hash.
3. Uploads are not transactional. A remote race or interrupted upload may leave unexpected remote state; do not rely on the preflight for adversarial concurrency.
4. The application does not sandbox Rclone or prevent an attacker running as the same Linux user from accessing Rclone credentials.
5. Hard links and directory-fd operations assume a local filesystem supporting these operations. An attacker with same-user access may interfere with staging; the stage path is not hardened against all hostile local concurrency. A machine crash can still leave temporary files.
6. GUI integration and end-to-end tests have not been run in this environment. Unit tests mock Rclone; they are **not** proof of data safety.
7. Only use disposable files and a test Proton account until integration tests and an independent audit are complete.

## Structure

- `run.py`: application launcher
- `secure_sync/gui.py`: GTK3 interface, manual confirmations and background workers
- `secure_sync/core.py`: validated Rclone commands, staging, no-clobber publishing
- `tests/test_core.py`: 11 unit tests including overwrite and simulated concurrent creation

## Suggested next milestone

Run live integration tests against a dedicated test remote; introduce a journal, cancellation, stronger stage-directory hardening and remote integrity verification where supported. Do not add automatic bidirectional synchronization until these are tested.
