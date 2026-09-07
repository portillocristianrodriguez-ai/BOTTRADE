import unittest

import review_safety_hardening as fix


class ReviewSafetyHardeningTests(unittest.TestCase):
    def test_cooldown_registry_no_borra_timestamp_con_pop(self):
        registry = fix._CooldownRegistry({"SOL/USD": 123.0})
        self.assertEqual(registry.pop("SOL/USD", None), 123.0)
        self.assertEqual(registry.get("SOL/USD"), 123.0)

    def test_held_es_estado_activo(self):
        order = type("Order", (), {"status": "held"})()
        self.assertTrue(fix._status_activo(order))

    def test_filled_no_es_estado_activo(self):
        order = type("Order", (), {"status": "filled"})()
        self.assertFalse(fix._status_activo(order))


if __name__ == "__main__":
    unittest.main()
