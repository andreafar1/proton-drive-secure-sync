"""Manual, non-deleting Rclone frontend. Not an audited Proton Drive client."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile

REMOTE_RE = re.compile(r'^[A-Za-z0-9_-]+:$')

class SyncError(Exception):
    pass

def validate_remote(remote: str) -> str:
    if not isinstance(remote, str) or not REMOTE_RE.fullmatch(remote):
        raise SyncError('Remote must be a configured Rclone name (e.g. proton:)')
    return remote

def validate_name(name: str) -> str:
    if not isinstance(name, str) or not name or name in ('.', '..') or '/' in name or '\\' in name or '\x00' in name:
        raise SyncError('Invalid file name')
    return name

def validate_path(path: str) -> str:
    if not isinstance(path, str) or not path or path.startswith('/') or '\\' in path or '\x00' in path or any(p in ('', '.', '..') for p in path.split('/')):
        raise SyncError('Invalid remote path')
    return path

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

class RcloneClient:
    def __init__(self, remote: str, binary: str = 'rclone', timeout: int = 1800):
        self.remote = validate_remote(remote)
        self.binary = binary
        self.timeout = timeout

    def _run(self, *args: str) -> str:
        try:
            proc = subprocess.run([self.binary, *args], capture_output=True, text=True,
                                  timeout=self.timeout, check=False,
                                  env={**os.environ, 'RCLONE_ASK_PASSWORD': 'false'})
        except (OSError, subprocess.TimeoutExpired) as e:
            raise SyncError(f'Rclone failed: {type(e).__name__}') from e
        if proc.returncode:
            # Never forward stdout/stderr: backend output may expose sensitive data.
            raise SyncError(f'Rclone exited with status {proc.returncode}')
        return proc.stdout

    def list_files(self) -> list[dict]:
        raw = self._run('lsjson', self.remote, '--files-only', '--recursive')
        try:
            items = json.loads(raw)
            if not isinstance(items, list):
                raise ValueError()
            result = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    path = validate_path(item['Path'])
                except (SyncError, KeyError):
                    continue
                size = item.get('Size')
                if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                    continue
                result.append({'path': path, 'size': size})
            return sorted(result, key=lambda f: f['path'])
        except (ValueError, TypeError) as e:
            raise SyncError('Unexpected Rclone listing') from e

    def upload(self, local: Path) -> str:
        local = Path(local)
        if local.is_symlink() or not local.is_file():
            raise SyncError('Select a regular, non-symlink file')
        name = validate_name(local.name)
        # Conservative preflight; does not eliminate remote concurrent-write races.
        existing = self.list_files()
        if any(item['path'] == name for item in existing):
            raise SyncError('Remote file already exists; refusing upload')
        target = self.remote + name
        self._run('copyto', str(local), target, '--immutable', '--retries', '1')
        return target

    def download(self, remote_path: str, destination_dir: Path) -> Path:
        remote_path = validate_path(remote_path)
        name = validate_name(PurePosixPath(remote_path).name)
        destdir = Path(destination_dir)
        # Open directory once, refuse symlink directories, and use dirfd operations.
        try:
            dirfd = os.open(destdir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as e:
            raise SyncError('Destination must be an existing non-symlink directory') from e
        try:
            try:
                os.stat(name, dir_fd=dirfd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise SyncError('Destination already exists; refusing overwrite')
            # Private stage in same directory to allow atomic hard-link publication.
            # Hard link fails safely if another process creates the target first.
            with tempfile.TemporaryDirectory(prefix='.pdss-', dir=destdir) as stage_dir:
                stage = Path(stage_dir) / name
                self._run('copyto', self.remote + remote_path, str(stage), '--retries', '1')
                if stage.is_symlink() or not stage.is_file():
                    raise SyncError('Download did not produce a regular file')
                before = sha256_file(stage)
                stage_fd = os.open(stage, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    st = os.fstat(stage_fd)
                    if not stat.S_ISREG(st.st_mode):
                        raise SyncError('Staged download is not a regular file')
                    os.fsync(stage_fd)
                finally:
                    os.close(stage_fd)
                if sha256_file(stage) != before:
                    raise SyncError('Staged download changed during verification')
                try:
                    os.link(stage, name, dst_dir_fd=dirfd, follow_symlinks=False)
                except FileExistsError as e:
                    raise SyncError('Destination appeared during transfer; refusing overwrite') from e
                os.fsync(dirfd)
            return destdir / name
        finally:
            os.close(dirfd)
