"""
A rendelési fotók beszédes fájlnevének tesztjei.

Futtatás:
    python3 backend/tests/test_photo_files.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lambda" / "common"))

from photo_files import PhotoMissing, archive_order_photos, photo_file_key  # noqa: E402

NOW = 1793952000  # 2026-11-06 UTC


def order(shipping):
    return {
        "orderId": "6e8b39cc-b8d8-45c6-a667-2aee95f3998f",
        "customer": {"name": "Kovács Éva Zsófia"},
        "shipping": shipping,
        "items": [
            {"productId": "led-talpas", "size": "20cm", "photoKey": "uploads/abc-csaladi_kep.JPG"},
            {"productId": "lampa-nelkul", "size": "15cm", "photoKey": "uploads/def-baba.png"},
        ],
    }


HOME = {"method": "home", "address": {"zip": "1105", "city": "Budapest", "address": "Maláta köz 4. 2/4/6"}}
FOXPOST = {"method": "foxpost", "lockerId": "hu123", "lockerName": "Allee bevásárlóközpont"}


class FakeS3:
    def __init__(self, missing=()):
        self.copies, self.missing = [], set(missing)

    def copy_object(self, Bucket, Key, CopySource, MetadataDirective):  # noqa: N803
        if CopySource["Key"] in self.missing:
            err = Exception("missing")
            err.response = {"Error": {"Code": "NoSuchKey"}}
            raise err
        self.copies.append((CopySource["Key"], Key))


class PhotoFileKeyTest(unittest.TestCase):
    def test_home_delivery_name(self):
        o = order(HOME)
        self.assertEqual(
            photo_file_key(o, 1, o["items"][0], now=NOW),
            "orders/2026-11-06/6E8B39CC_Kovacs-Eva-Zsofia_1105-Budapest-Malata-koz-4-2-4-6_1-LED-20cm.jpg",
        )

    def test_foxpost_name_and_png(self):
        o = order(FOXPOST)
        self.assertEqual(
            photo_file_key(o, 2, o["items"][1], now=NOW),
            "orders/2026-11-06/6E8B39CC_Kovacs-Eva-Zsofia_Foxpost-Allee-bevasarlokozpont_2-lampa-nelkul-15cm.png",
        )

    def test_hostile_input_stays_in_folder(self):
        o = order(HOME)
        o["customer"]["name"] = "../../etc/passwd"
        key = photo_file_key(o, 1, o["items"][0], now=NOW)
        self.assertTrue(key.startswith("orders/2026-11-06/6E8B39CC_etc-passwd_"))
        self.assertNotIn("..", key)


class ArchiveTest(unittest.TestCase):
    def test_copies_every_item(self):
        o, s3 = order(HOME), FakeS3()
        archive_order_photos(o, s3, "bucket")
        self.assertEqual(len(s3.copies), 2)
        self.assertTrue(all(i["photoFile"].startswith("orders/") for i in o["items"]))
        self.assertEqual(o["items"][0]["photoKey"], "uploads/abc-csaladi_kep.JPG")  # az eredeti megmarad

    def test_missing_upload(self):
        o = order(HOME)
        with self.assertRaises(PhotoMissing):
            archive_order_photos(o, FakeS3(missing={"uploads/def-baba.png"}), "bucket")

    def test_rejects_foreign_key(self):
        o = order(HOME)
        o["items"][0]["photoKey"] = "cache/foxpost.json"
        with self.assertRaises(PhotoMissing):
            archive_order_photos(o, FakeS3(), "bucket")


if __name__ == "__main__":
    unittest.main()
