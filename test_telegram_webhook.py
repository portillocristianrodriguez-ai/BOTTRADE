import hashlib
import unittest

import telegram_webhook


class TelegramWebhookTests(unittest.TestCase):
    def test_secret_is_deterministic_and_does_not_expose_token(self):
        original = telegram_webhook.config.TELEGRAM_BOT_TOKEN
        try:
            telegram_webhook.config.TELEGRAM_BOT_TOKEN = "123456:TEST_SECRET"
            expected = hashlib.sha256(b"123456:TEST_SECRET").hexdigest()[:48]
            self.assertEqual(telegram_webhook._secret(), expected)
            self.assertNotIn("123456:TEST_SECRET", telegram_webhook.webhook_path())
        finally:
            telegram_webhook.config.TELEGRAM_BOT_TOKEN = original

    def test_webhook_path_is_namespaced(self):
        self.assertTrue(telegram_webhook.webhook_path().startswith("/telegram/"))


if __name__ == "__main__":
    unittest.main()
