import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import persistent_worker_entrypoint as entry


class PersistentWorkerTests(unittest.TestCase):
    def test_requires_restored_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(entry.data_ready(folder))
            Path(folder, '.bottrade-restored').write_text('verified')
            self.assertTrue(entry.data_ready(folder))

    def test_live_mode_cannot_start(self):
        with patch.dict('os.environ', {'ALPACA_PAPER': 'false'}):
            with self.assertRaisesRegex(RuntimeError, 'PAPER'):
                entry.main()

    def test_uses_persistent_working_directory_before_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, '.bottrade-restored').write_text('verified')
            with patch.dict('os.environ', {'ALPACA_PAPER':'true', 'BOTTRADE_DATA_DIR':folder}), patch.object(entry.os, 'chdir') as cd, patch.object(entry.os, 'execv') as run:
                entry.main()
            cd.assert_called_once_with(Path(folder).resolve())
            self.assertTrue(run.call_args.args[1][1].endswith('worker_entrypoint.py'))
