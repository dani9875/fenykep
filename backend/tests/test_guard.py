"""
A visszaélés elleni védelem tesztjei (backend/lambda/common/guard.py).

AWS nem kell hozzá: a DynamoDB számlálót egy memóriabeli duplikátum
helyettesíti.

Futtatás:
    python3 backend/tests/test_guard.py
"""

import os
import sys
import types
import unittest
from pathlib import Path

COMMON = Path(__file__).resolve().parents[1] / "lambda" / "common"
sys.path.insert(0, str(COMMON))

os.environ["RATE_LIMIT_TABLE"] = "test-ratelimit"
os.environ["ALLOWED_ORIGINS"] = "https://fenykep.pages.dev,http://localhost:8787"
os.environ["ENFORCE_ORIGIN"] = "true"


class FakeRateTable:
    """Annyi DynamoDB, amennyit a guard használ: atomi ADD számláló."""

    def __init__(self):
        self.counts = {}
        self.fail = False

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues, ReturnValues):  # noqa: N803
        if self.fail:
            raise RuntimeError("DynamoDB nem elérhető")
        key = Key["rateKey"]
        self.counts[key] = self.counts.get(key, 0) + ExpressionAttributeValues[":one"]
        return {"Attributes": {"hits": self.counts[key]}}


fake_table = FakeRateTable()

fake_boto3 = types.ModuleType("boto3")
fake_boto3.resource = lambda *a, **k: types.SimpleNamespace(Table=lambda name: fake_table)
sys.modules["boto3"] = fake_boto3

import guard  # noqa: E402


def event(origin=None, referer=None, ip="1.2.3.4", body=""):
    headers = {}
    if origin:
        headers["origin"] = origin
    if referer:
        headers["referer"] = referer
    return {
        "headers": headers,
        "body": body,
        "requestContext": {"http": {"sourceIp": ip}},
    }


class OriginTest(unittest.TestCase):
    def test_allowed_origin_passes(self):
        guard.check_origin(event(origin="https://fenykep.pages.dev"))  # nem dob

    def test_trailing_slash_is_tolerated(self):
        guard.check_origin(event(origin="https://fenykep.pages.dev/"))

    def test_foreign_origin_is_rejected(self):
        with self.assertRaises(guard.Rejected) as ctx:
            guard.check_origin(event(origin="https://rosszfiu.example"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_missing_origin_is_rejected(self):
        """Curl és a legtöbb szkript nem küld Origin fejlécet."""
        with self.assertRaises(guard.Rejected):
            guard.check_origin(event())

    def test_referer_is_accepted_as_fallback(self):
        guard.check_origin(event(referer="https://fenykep.pages.dev/penztar.html"))

    def test_can_be_switched_off(self):
        guard.ENFORCE_ORIGIN = False
        try:
            guard.check_origin(event(origin="https://rosszfiu.example"))
        finally:
            guard.ENFORCE_ORIGIN = True


class RateLimitTest(unittest.TestCase):
    def setUp(self):
        fake_table.counts.clear()
        fake_table.fail = False

    def test_allows_up_to_the_limit_then_rejects(self):
        for i in range(5):
            guard.rate_limit(event(), "orders", limit=5)
        with self.assertRaises(guard.Rejected) as ctx:
            guard.rate_limit(event(), "orders", limit=5)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Túl sok kérés", ctx.exception.message)

    def test_counts_per_ip(self):
        for i in range(5):
            guard.rate_limit(event(ip="1.1.1.1"), "orders", limit=5)
        # Egy másik IP-t ez nem érint.
        guard.rate_limit(event(ip="2.2.2.2"), "orders", limit=5)

    def test_counts_per_bucket(self):
        for i in range(5):
            guard.rate_limit(event(), "orders", limit=5)
        guard.rate_limit(event(), "uploads", limit=5)  # másik végpont, külön keret

    def test_database_error_lets_the_request_through(self):
        """Egy adatbázishiba ne tegye használhatatlanná a webshopot."""
        fake_table.fail = True
        guard.rate_limit(event(), "orders", limit=1)
        guard.rate_limit(event(), "orders", limit=1)

    def test_rejection_carries_a_retry_hint(self):
        with self.assertRaises(guard.Rejected) as ctx:
            for i in range(3):
                guard.rate_limit(event(), "orders", limit=1)
        body = ctx.exception.response({"Content-Type": "application/json"})
        self.assertEqual(body["statusCode"], 429)
        self.assertIn("retryAfterSeconds", body["body"])


class BodySizeTest(unittest.TestCase):
    def test_oversized_body_is_rejected(self):
        with self.assertRaises(guard.Rejected) as ctx:
            guard.check_body_size(event(body="x" * (guard.MAX_BODY_BYTES + 1)))
        self.assertEqual(ctx.exception.status_code, 413)

    def test_normal_body_passes(self):
        guard.check_body_size(event(body='{"customer": {}}'))


class ProtectTest(unittest.TestCase):
    def setUp(self):
        fake_table.counts.clear()
        fake_table.fail = False

    def test_protect_runs_every_check(self):
        good = event(origin="https://fenykep.pages.dev")
        guard.protect(good, bucket="orders", limit=2)

        with self.assertRaises(guard.Rejected):  # idegen origin
            guard.protect(event(origin="https://rosszfiu.example"), bucket="orders", limit=2)

        guard.protect(good, bucket="orders", limit=2)
        with self.assertRaises(guard.Rejected):  # kimerült keret
            guard.protect(good, bucket="orders", limit=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
