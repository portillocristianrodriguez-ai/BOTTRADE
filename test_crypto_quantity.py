import unittest
from decimal import Decimal

from crypto_quantity import normalizar_cantidad_crypto


class TestCryptoQuantity(unittest.TestCase):
    def test_floor_to_increment_with_safety_margin(self):
        self.assertEqual(
            normalizar_cantidad_crypto("109379.12345", "0.0001"),
            Decimal("109379.0234"),
        )

    def test_exact_multiple_gets_safety_buffer(self):
        self.assertEqual(
            normalizar_cantidad_crypto("109379", "1"),
            Decimal("108379"),
        )

    def test_pepe_like_precision_error(self):
        qty = normalizar_cantidad_crypto("2428548997.2046323", None)
        self.assertEqual(qty, Decimal("2428548997.204631300"))
        self.assertLess(qty, Decimal("2428548997.204632123"))

    def test_dust_becomes_zero(self):
        qty = normalizar_cantidad_crypto("0.000000823", None)
        self.assertEqual(qty, Decimal("0"))

    def test_invalid_or_non_positive(self):
        self.assertEqual(normalizar_cantidad_crypto("nope", "0.0001"), Decimal("0"))
        self.assertEqual(normalizar_cantidad_crypto("0", "0.0001"), Decimal("0"))


if __name__ == "__main__":
    unittest.main()
