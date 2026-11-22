import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from secure_sync.core import RcloneClient, SyncError, validate_remote, validate_path, sha256_file

class CoreTests(unittest.TestCase):
    def test_remote_validation(self):
        self.assertEqual(validate_remote('proton:'), 'proton:')
        for v in ('proton:/x', 'foo;rm:', '', '../x:', 'remote:folder'):
            with self.assertRaises(SyncError): validate_remote(v)

    def test_path_validation(self):
        for v in ('../x', '/absolute', 'a//b', 'a/./b', 'a/../b', 'a\\b', ''):
            with self.assertRaises(SyncError): validate_path(v)

    @patch('secure_sync.core.subprocess.run')
    def test_listing(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = json.dumps([{'Path':'a.txt','Size':2},{'Path':'../bad','Size':1}])
        self.assertEqual(RcloneClient('proton:').list_files(), [{'path':'a.txt','size':2}])

    def test_upload_refuses_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'a.txt'; p.write_text('x')
            with patch.object(RcloneClient, 'list_files', return_value=[{'path':'a.txt','size':1}]):
                with self.assertRaises(SyncError): RcloneClient('proton:').upload(p)

    def test_upload_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'a.txt'; p.write_text('x')
            c = RcloneClient('proton:')
            with patch.object(c, 'list_files', return_value=[]), patch.object(c, '_run', return_value='') as run:
                c.upload(p)
                self.assertIn('--immutable', run.call_args.args)

    def test_download_refuses_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)/'a.txt'; dest.write_text('keep')
            with self.assertRaises(SyncError): RcloneClient('proton:').download('a.txt', Path(tmp))
            self.assertEqual(dest.read_text(), 'keep')

    def test_download_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SyncError): RcloneClient('proton:').download('../a.txt', Path(tmp))

    def test_download_atomic_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = RcloneClient('proton:')
            def fake_run(*args):
                Path(args[2]).write_bytes(b'complete payload')
                return ''
            with patch.object(c, '_run', side_effect=fake_run):
                dest = c.download('folder/a.txt', Path(tmp))
            self.assertEqual(dest.read_bytes(), b'complete payload')
            self.assertEqual(sha256_file(dest), sha256_file(dest))

    def test_download_failed_transfer_leaves_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = RcloneClient('proton:')
            with patch.object(c, '_run', side_effect=SyncError('network')):
                with self.assertRaises(SyncError): c.download('a.txt', Path(tmp))
            self.assertFalse((Path(tmp)/'a.txt').exists())

    def test_download_concurrent_creation_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = RcloneClient('proton:')
            def fake_run(*args):
                Path(args[2]).write_bytes(b'new')
                (Path(tmp)/'a.txt').write_bytes(b'other writer')
                return ''
            with patch.object(c, '_run', side_effect=fake_run):
                with self.assertRaises(SyncError): c.download('a.txt', Path(tmp))
            self.assertEqual((Path(tmp)/'a.txt').read_bytes(), b'other writer')

    def test_download_refuses_symlink_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp)/'real'; real.mkdir()
            link = Path(tmp)/'link'; link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(SyncError): RcloneClient('proton:').download('a.txt', link)

if __name__ == '__main__': unittest.main()
