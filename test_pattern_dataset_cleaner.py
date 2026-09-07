import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pattern_dataset_cleaner import limpiar, sanitize_record


class DatasetTests(unittest.TestCase):
    def test_preserves_valid_lines_and_malformed_records_with_exact_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'pattern_observations.jsonl'
            valid = b'{"ticker":"NVDA", "volume_ratio":2.5,"future_returns":{"5":1.2}}\n'
            bad = b'{"ticker":"BONK/USD","volume_ratio":620000000000,"scanner":{"volumen_ratio":NaN},"price":0.00001}\n'
            malformed = b'{broken\n'
            original = valid + malformed + bad
            path.write_bytes(original)
            config = SimpleNamespace(PATTERN_DATA_FILE=str(path))
            self.assertEqual(limpiar(config), 2)
            self.assertTrue(path.read_bytes().startswith(valid + malformed))
            fixed = json.loads(path.read_bytes().splitlines()[-1])
            self.assertIsNone(fixed['volume_ratio'])
            self.assertIsNone(fixed['scanner']['volumen_ratio'])
            self.assertEqual(fixed['price'], 0.00001)
            self.assertEqual(next(Path(folder).glob('*.backup-*')).read_bytes(), original)
            self.assertEqual(limpiar(config), 0)

    def test_invalid_reference_invalidates_nested_ratio_without_erasing_returns(self):
        row = dict(scanner=dict(volumen_media=0, volumen_ratio=3), future_returns={'5': -1.5})
        self.assertEqual(sanitize_record(row), 2)
        self.assertIsNone(row['scanner']['volumen_ratio'])
        self.assertEqual(row['future_returns']['5'], -1.5)
        json.dumps(row, allow_nan=False)
