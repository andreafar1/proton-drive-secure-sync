"""Unit tests for the conservative scheduler; Rclone is mocked."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import scheduler

class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_db, self.old_root = scheduler.DB, scheduler.LOCAL_ROOT
        scheduler.DB = self.root / 'state.sqlite3'
        scheduler.LOCAL_ROOT = self.root / 'sync'
        scheduler.LOCAL_ROOT.mkdir()
        (scheduler.LOCAL_ROOT / 'Documents').mkdir()

    def tearDown(self):
        scheduler.DB, scheduler.LOCAL_ROOT = self.old_db, self.old_root
        self.tmp.cleanup()

    def job(self, **updates):
        data = dict(name='Documenti', direction='upload', local_path='Documents',
                    remote_path='Backup/Documenti', interval_minutes=60)
        data.update(updates)
        return data

    def test_create_disabled(self):
        job_id = scheduler.add_job(self.job())
        job = scheduler.list_jobs()[0]
        self.assertEqual(job['id'], job_id)
        self.assertEqual(job['enabled'], 0)

    def test_bad_remote_path(self):
        with self.assertRaises(ValueError):
            scheduler.add_job(self.job(remote_path='../secret'))

    def test_bad_local_escape(self):
        with self.assertRaises(Exception):
            scheduler.add_job(self.job(local_path='../secret'))

    def test_manual_job_cannot_enable(self):
        job_id = scheduler.add_job(self.job(interval_minutes=0))
        with self.assertRaises(ValueError):
            scheduler.toggle_job(job_id, True)

    def test_enabled_job_has_next_run(self):
        job_id = scheduler.add_job(self.job())
        scheduler.toggle_job(job_id, True)
        self.assertIsNotNone(scheduler.list_jobs()[0]['next_run'])

    def test_one_way_rclone_copy_ignores_existing(self):
        job_id = scheduler.add_job(self.job())
        scheduler.request_run(job_id)
        with patch('scheduler.subprocess.run') as run:
            run.return_value.returncode = 0
            self.assertTrue(scheduler.tick())
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[1], 'copy')
            self.assertIn('--ignore-existing', cmd)
            self.assertNotIn('sync', cmd[:2])
        self.assertEqual(scheduler.list_jobs()[0]['last_status'], 'Completato')

    def test_delete_job_does_not_touch_files(self):
        f = scheduler.LOCAL_ROOT / 'Documents' / 'keep.txt'
        f.write_text('keep')
        job_id = scheduler.add_job(self.job())
        scheduler.delete_job(job_id)
        self.assertEqual(f.read_text(), 'keep')

if __name__ == '__main__':
    unittest.main()
