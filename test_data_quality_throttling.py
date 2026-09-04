import unittest
from unittest.mock import patch

import data_quality_hardening


class DataQualityThrottlingTests(unittest.TestCase):
    def test_warning_is_rate_limited_per_symbol(self):
        data_quality_hardening._last_warning.clear()
        with patch.object(data_quality_hardening.log, "warning") as warning:
            with patch.object(data_quality_hardening.time, "monotonic", return_value=100.0):
                data_quality_hardening._avisar_historial_insuficiente("TEST", 10, 50)
                data_quality_hardening._avisar_historial_insuficiente("TEST", 11, 50)
            self.assertEqual(warning.call_count, 1)

    def test_different_symbols_are_logged_independently(self):
        data_quality_hardening._last_warning.clear()
        with patch.object(data_quality_hardening.log, "warning") as warning:
            with patch.object(data_quality_hardening.time, "monotonic", return_value=100.0):
                data_quality_hardening._avisar_historial_insuficiente("AAA", 10, 50)
                data_quality_hardening._avisar_historial_insuficiente("BBB", 10, 50)
            self.assertEqual(warning.call_count, 2)


if __name__ == "__main__":
    unittest.main()
