"""
A fizetés-egyeztetés tesztjei.

Nem kell hozzá AWS: a DynamoDB táblát és az SES-t egy-egy memóriabeli
duplikátum helyettesíti, a Barion PaymentState válaszát pedig beadjuk.

Futtatás:
    python3 backend/tests/test_payments.py
"""

import sys
import types
import unittest
from pathlib import Path

COMMON = Path(__file__).resolve().parents[1] / "lambda" / "common"
sys.path.insert(0, str(COMMON))


# ---------------------------------------------------------------- stubs
class FakeConditionalCheckFailed(Exception):
    pass


class FakeTable:
    """Annyi DynamoDB, amennyit a dynamo.py használ — a feltételes írással együtt."""

    def __init__(self):
        self.items = {}

    def put_item(self, Item):  # noqa: N803 - boto3 névkonvenció
        self.items[Item["orderId"]] = dict(Item)

    def get_item(self, Key):  # noqa: N803
        item = self.items.get(Key["orderId"])
        return {"Item": dict(item)} if item else {}

    def query(self, **kwargs):
        return {"Items": []}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeNames,  # noqa: N803
                    ExpressionAttributeValues, ConditionExpression=None):
        item = self.items[Key["orderId"]]
        if ConditionExpression is not None:
            allowed = {v for k, v in ExpressionAttributeValues.items() if k.startswith(":f")}
            if item.get("orderStatus") not in allowed:
                raise FakeConditionalCheckFailed()
        for assignment in UpdateExpression[len("SET "):].split(", "):
            target, source = [part.strip() for part in assignment.split("=")]
            name = ExpressionAttributeNames.get(target, target)
            item[name] = ExpressionAttributeValues[source]


fake_table = FakeTable()

fake_boto3 = types.ModuleType("boto3")
fake_boto3.resource = lambda *a, **k: types.SimpleNamespace(
    Table=lambda name: fake_table,
    meta=types.SimpleNamespace(
        client=types.SimpleNamespace(
            exceptions=types.SimpleNamespace(ConditionalCheckFailedException=FakeConditionalCheckFailed)
        )
    ),
)
fake_boto3.client = lambda *a, **k: types.SimpleNamespace(send_email=lambda **kw: sent_emails.append(kw))
sys.modules["boto3"] = fake_boto3

fake_conditions = types.ModuleType("boto3.dynamodb.conditions")
fake_conditions.Key = lambda name: types.SimpleNamespace(eq=lambda value: None)
sys.modules["boto3.dynamodb"] = types.ModuleType("boto3.dynamodb")
sys.modules["boto3.dynamodb.conditions"] = fake_conditions

sent_emails = []

import barion  # noqa: E402
import payments  # noqa: E402


def make_order(status="pending_payment", total=11480):
    return {
        "orderId": "order-1",
        "orderStatus": status,
        "paymentMethod": "barion",
        "paymentId": "pay-1",
        "totalHuf": total,
        "subtotalHuf": total - 1490,
        "shippingFeeHuf": 1490,
        "customer": {"name": "Teszt Elek", "email": "teszt@example.com", "phone": "+36301234567",
                     "address": "Fő utca 1", "city": "Budapest", "zip": "1053"},
        "shipping": {"method": "foxpost", "lockerName": "Teszt automata", "feeHuf": 1490},
        "items": [{"productName": "Litofán", "size": "15cm", "qty": 1, "unitPrice": 9990, "photoKey": "k.jpg"}],
    }


class PaymentReconcileTest(unittest.TestCase):
    def setUp(self):
        fake_table.items.clear()
        sent_emails.clear()
        self.order = make_order()
        fake_table.put_item(Item=self.order)

    def reconcile_with(self, state):
        payments.barion.get_payment_state = lambda payment_id: state
        return payments.reconcile(dict(fake_table.items["order-1"]))

    def stored_status(self):
        return fake_table.items["order-1"]["orderStatus"]

    def subjects(self):
        return [e["Message"]["Subject"]["Data"] for e in sent_emails]

    # ---- sikeres fizetés ----
    def test_succeeded_marks_paid_and_sends_two_emails(self):
        result = self.reconcile_with({"Status": "Succeeded", "Total": 11480, "Currency": "HUF"})
        self.assertEqual(result["orderStatus"], "paid")
        self.assertEqual(self.stored_status(), "paid")
        self.assertEqual(len(sent_emails), 2)  # vásárló + admin

    def test_repeated_callback_does_not_send_a_second_confirmation(self):
        state = {"Status": "Succeeded", "Total": 11480, "Currency": "HUF"}
        self.reconcile_with(state)
        sent_emails.clear()
        self.reconcile_with(state)  # a Barion újrahívja ugyanazt
        self.assertEqual(self.stored_status(), "paid")
        self.assertEqual(sent_emails, [])

    def test_total_from_transactions_when_top_level_missing(self):
        result = self.reconcile_with({"Status": "Succeeded", "Transactions": [{"Total": 11480}], "Currency": "HUF"})
        self.assertEqual(result["orderStatus"], "paid")

    # ---- hibás összeg ----
    def test_amount_mismatch_does_not_fulfil(self):
        result = self.reconcile_with({"Status": "Succeeded", "Total": 1000, "Currency": "HUF"})
        self.assertEqual(result["orderStatus"], "payment_mismatch")
        self.assertEqual(self.stored_status(), "payment_mismatch")
        self.assertEqual(len(sent_emails), 1)  # csak az admin kap értesítést
        self.assertIn("eltérő fizetett összeg", self.subjects()[0].lower())

    def test_wrong_currency_does_not_fulfil(self):
        result = self.reconcile_with({"Status": "Succeeded", "Total": 11480, "Currency": "EUR"})
        self.assertEqual(result["orderStatus"], "payment_mismatch")

    def test_unreadable_total_does_not_fulfil(self):
        result = self.reconcile_with({"Status": "Succeeded"})
        self.assertEqual(result["orderStatus"], "payment_mismatch")

    # ---- sikertelen ágak ----
    def test_failed_canceled_expired_map_to_own_statuses(self):
        for barion_status, expected in (
            ("Failed", "payment_failed"),
            ("Canceled", "payment_canceled"),
            ("Expired", "payment_expired"),
        ):
            with self.subTest(barion_status):
                self.setUp()
                result = self.reconcile_with({"Status": barion_status})
                self.assertEqual(result["orderStatus"], expected)
                self.assertEqual(len(sent_emails), 1)  # egy értesítés a vásárlónak

    def test_repeated_failure_callback_sends_one_email(self):
        self.reconcile_with({"Status": "Failed"})
        sent_emails.clear()
        self.reconcile_with({"Status": "Failed"})
        self.assertEqual(sent_emails, [])

    def test_failed_payment_can_still_succeed_later(self):
        """Barion-oldali újrapróbálkozás: a sikertelenből lehet fizetett."""
        self.reconcile_with({"Status": "Failed"})
        sent_emails.clear()
        result = self.reconcile_with({"Status": "Succeeded", "Total": 11480, "Currency": "HUF"})
        self.assertEqual(result["orderStatus"], "paid")
        self.assertEqual(len(sent_emails), 2)

    def test_partially_succeeded_goes_to_manual_review(self):
        result = self.reconcile_with({"Status": "PartiallySucceeded", "Total": 11480, "Currency": "HUF"})
        self.assertEqual(result["orderStatus"], "payment_review")
        self.assertEqual(len(sent_emails), 1)

    # ---- köztes és hibás állapotok ----
    def test_pending_statuses_leave_the_order_alone(self):
        for status in ("Prepared", "Started", "InProgress", "Waiting", "Reserved", "Authorized"):
            with self.subTest(status):
                self.setUp()
                result = self.reconcile_with({"Status": status})
                self.assertEqual(result["orderStatus"], "pending_payment")
                self.assertEqual(sent_emails, [])

    def test_unknown_status_is_recorded_but_not_acted_on(self):
        result = self.reconcile_with({"Status": "SomethingNew"})
        self.assertEqual(result["orderStatus"], "pending_payment")
        self.assertEqual(fake_table.items["order-1"]["paymentStatus"], "SomethingNew")
        self.assertEqual(sent_emails, [])

    def test_barion_error_leaves_the_order_open(self):
        def boom(payment_id):
            raise barion.BarionError("hálózati hiba")

        payments.barion.get_payment_state = boom
        result = payments.reconcile(dict(fake_table.items["order-1"]))
        self.assertEqual(result["orderStatus"], "pending_payment")
        self.assertEqual(self.stored_status(), "pending_payment")

    def test_throttling_is_not_treated_as_a_failure(self):
        def throttled(payment_id):
            raise barion.BarionThrottledError("429")

        payments.barion.get_payment_state = throttled
        result = payments.reconcile(dict(fake_table.items["order-1"]))
        self.assertEqual(result["orderStatus"], "pending_payment")

    def test_ses_failure_does_not_break_the_callback(self):
        """Az email elakadása nem dobhat kivételt: a callbacknek 200-at kell adnia."""
        original = payments.send_customer_confirmation
        payments.send_customer_confirmation = lambda order: (_ for _ in ()).throw(RuntimeError("SES le van tiltva"))
        try:
            result = self.reconcile_with({"Status": "Succeeded", "Total": 11480, "Currency": "HUF"})
        finally:
            payments.send_customer_confirmation = original
        self.assertEqual(result["orderStatus"], "paid")  # a rendelés attól még fizetett
        # ...és a hiba nyoma rákerül a rendelésre, hogy ne csak a logból derüljön ki
        self.assertIn("SES le van tiltva", fake_table.items["order-1"].get("emailError", ""))

    def test_non_card_orders_are_skipped(self):
        fake_table.items["order-1"]["paymentMethod"] = "transfer"
        result = payments.reconcile(dict(fake_table.items["order-1"]))
        self.assertEqual(result["paymentStatus"], None)


class BarionRequestTest(unittest.TestCase):
    """A Payment/Start törzsének összeállítása — hálózat nélkül."""

    def setUp(self):
        barion.POSKEY = "test-poskey"
        barion.PAYEE = "shop@example.com"
        barion.REDIRECT_URL = "https://example.hu/koszonjuk.html"
        barion.CALLBACK_URL = "https://api.example.hu/barion-callback"
        self.captured = {}

        def fake_request(method, path, body=None, headers=None):
            self.captured.update({"method": method, "path": path, "body": body, "headers": headers})
            return {"PaymentId": "pay-1", "GatewayUrl": "https://barion.example/pay"}

        barion._request = fake_request

    def start(self, **kwargs):
        items = [{"name": "Litofán (15cm)", "qty": 1, "unit_price": 9990},
                 {"name": "Foxpost szállítás", "qty": 1, "unit_price": 1490}]
        return barion.start_payment("order-1", items, 11480, **kwargs)

    def test_body_has_the_fields_barion_expects(self):
        self.start(customer={"name": "Teszt Elek", "email": "t@example.com", "phone": "+36 30 123 4567",
                             "address": "Fő utca 1", "city": "Budapest", "zip": "1053"})
        body = self.captured["body"]
        self.assertEqual(body["PaymentRequestId"], "order-1")
        self.assertEqual(body["OrderNumber"], "order-1")
        self.assertEqual(body["Currency"], "HUF")
        self.assertEqual(body["Locale"], "hu-HU")
        self.assertEqual(body["Transactions"][0]["Total"], 11480)
        self.assertEqual(body["CallbackUrl"], "https://api.example.hu/barion-callback")
        self.assertIn("orderId=order-1", body["RedirectUrl"])
        self.assertEqual(body["BillingAddress"]["Zip"], "1053")

    def test_only_bank_card_is_offered_by_default(self):
        """Alapból csak kártyás fizetés — a Barion tárca-belépés ne jöjjön fel."""
        self.start()
        self.assertEqual(self.captured["body"]["FundingSources"], ["BankCard"])
        self.assertTrue(self.captured["body"]["GuestCheckOut"])

    def test_phone_is_normalised_for_barion(self):
        cases = {"+36 30 123 4567": "36301234567", "06301234567": "36301234567",
                 "301234567": "36301234567", "": "", "nem szám": ""}
        for raw, expected in cases.items():
            with self.subTest(raw):
                self.assertEqual(barion._phone_for_barion(raw), expected)

    def test_item_sum_must_match_the_total(self):
        with self.assertRaises(barion.BarionError):
            barion.start_payment("order-1", [{"name": "X", "qty": 1, "unit_price": 100}], 99999)

    def test_payment_state_uses_the_v4_endpoint_with_the_pos_key_header(self):
        barion.get_payment_state("pay-1")
        self.assertEqual(self.captured["path"], "/v4/Payment/pay-1/PaymentState")
        self.assertEqual(self.captured["headers"], {"x-pos-key": "test-poskey"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
