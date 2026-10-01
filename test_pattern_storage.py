import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pattern_storage as storage


class PatternStorageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name, 'pattern_observations.jsonl')
        self.rows = [json.dumps({'i': i}).encode() + b'\n' for i in range(100)]
        self.original = b''.join(self.rows)
        self.path.write_bytes(self.original)

    def test_retains_complete_recent_lines_and_protects_state(self):
        state = self.path.with_name('bot_state.json')
        state.write_bytes(b'protected')
        removed = storage.compact(self.path, 200, 100)
        kept = self.path.read_bytes()
        self.assertLessEqual(len(kept), 100)
        self.assertTrue(self.original.endswith(kept))
        self.assertEqual(json.loads(kept.splitlines()[-1]), {'i': 99})
        self.assertEqual(removed, len(self.original) - len(kept))
        self.assertEqual(state.read_bytes(), b'protected')
        self.assertEqual(storage.compact(self.path, 200, 100), 0)

    def test_preserves_line_at_exact_boundary(self):
        size = sum(map(len, self.rows[-10:]))
        storage.compact(self.path, 2 * size, size)
        self.assertEqual(self.path.read_bytes(), b''.join(self.rows[-10:]))

    def test_interrupted_append_drops_only_partial_last_line(self):
        self.path.write_bytes(self.original + b'{"i":')
        storage.compact(self.path, 200, 100)
        self.assertEqual(json.loads(self.path.read_bytes().splitlines()[-1]), {'i': 99})

    def test_sync_failure_preserves_suffix_for_retry(self):
        tail = self.original[-100:]
        with patch.object(storage.os, 'fsync', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                storage.compact(self.path, 200, 100)
        self.assertEqual(self.path.stat().st_size, len(self.original))
        self.assertTrue(self.path.read_bytes().endswith(tail))
        storage.compact(self.path, 200, 100)
        self.assertEqual(json.loads(self.path.read_bytes().splitlines()[-1]), {'i': 99})

    def test_refuses_other_files_symlinks_and_hardlinks(self):
        with self.assertRaises(ValueError):
            storage.compact(self.path.with_name('bot_state.json'), 200, 100)
        self.path.unlink()
        target = self.path.with_name('bot_state.json')
        target.write_bytes(self.original)
        self.path.symlink_to(target)
        with self.assertRaises(OSError):
            storage.compact(self.path, 200, 100)
        self.path.unlink()
        self.path.hardlink_to(target)
        with self.assertRaises(ValueError):
            storage.compact(self.path, 200, 100)
        self.assertEqual(target.read_bytes(), self.original)

    def test_missing_small_or_unrecoverable_file(self):
        self.path.unlink()
        self.assertEqual(storage.compact(self.path, 200, 100), 0)
        self.path.write_bytes(b'x' * 300)
        with self.assertRaises(ValueError):
            storage.compact(self.path, 200, 100)
        self.assertEqual(self.path.read_bytes(), b'x' * 300)
        with self.assertRaises(ValueError):
            storage.compact(self.path, 200, 101)

    def test_wrapper_bounds_parallel_appends_and_preserves_result(self):
        self.path.write_bytes(b'')
        def append(i):
            with self.path.open('ab') as handle:
                handle.write(json.dumps({'i': i}).encode() + b'\n')
            return 'result'
        module = SimpleNamespace(config=SimpleNamespace(PATTERN_DATA_FILE=self.path), registrar_observacion_pattern=append)
        storage.install(module)
        wrapped = module.registrar_observacion_pattern
        storage.install(module)
        self.assertIs(module.registrar_observacion_pattern, wrapped)
        real_compact = storage.compact
        with patch.object(storage, 'compact', side_effect=lambda path: real_compact(path, 200, 100)):
            threads = [threading.Thread(target=wrapped, args=(i,)) for i in range(100)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(wrapped(999), 'result')
        self.assertLessEqual(self.path.stat().st_size, 200)
        rows = [json.loads(line) for line in self.path.read_bytes().splitlines()]
        self.assertEqual(rows[-1], {'i': 999})
