import unittest
from decimal import Decimal

from crypto_quantity import normalizar_cantidad_crypto


class TestCryptoQuantity(unittest.TestCase):
    def test_floor_to_increment(self):
        self.assertEqual(
            normalizar_cantidad_crypto("109379.12345", "0.0001"),
            Decimal("109379.1234"),
        )

    def test_exact_multiple_gets_one_safety_increment(self):
        self.assertEqual(
            normalizar_cantidad_crypto("109379", "1"),
            Decimal("109378"),
        )

    def test_pepe_like_precision_error(self):
        self.assertEqual(
            normalizar_cantidad_crypto("109379", "0.000001"),
            Decimal("109378.999999"),
        )

    def test_invalid_or_non_positive(self):
        self.assertEqual(normalizar_cantidad_crypto("nope", "0.0001"), Decimal("0"))
        self.assertEqual(normalizar_cantidad_crypto("0", "0.0001"), Decimal("0"))


if __name__ == "__main__":
    unittest.main()
