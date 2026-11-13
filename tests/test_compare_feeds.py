"""Synthetic fixtures; never interpreted as market evidence."""
import csv
import hashlib
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from goldintel.data.compare_feeds import compare_feeds
from goldintel.data.mt5_csv import COLUMNS, MarketDataError


class CompareFeedsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, values):
        path = self.root / name
        with path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(COLUMNS)
            for time, price in values:
                price = Decimal(str(price))
                writer.writerow(["XAUUSD", "M15", "2026.03.03 " + time,
                                 price, price + 1, price - 1, price, 10, 20, 0])
        return path

    def compare(self, a, b, **kwargs):
        return compare_feeds(a, b, left_symbol="XAUUSD", right_symbol="XAUUSD", **kwargs)

    def test_exact_threshold_groups_and_immutable_inputs(self):
        times = ["03:00:00", "03:15:00", "03:30:00", "03:45:00", "04:00:00"]
        a = self.write("a.csv", zip(times, [2006, 2007, 2005, 2008, 2009]))
        b = self.write("b.csv", zip(times, [2000] * 5))
        before = a.read_bytes(), b.read_bytes()
        r = self.compare(a, b)
        self.assertEqual(len(r["outliers"]), 4)
        self.assertEqual([g["candles"] for g in r["consecutive_outlier_groups"]], [2, 2])
        self.assertEqual(len(r["nonoverlapping_ranges"]), 5)
        self.assertFalse(r["utc_verified"])
        self.assertFalse(r["training_ready"])
        self.assertEqual(before, (a.read_bytes(), b.read_bytes()))
        self.assertEqual(r, self.compare(a, b))

    def test_unmatched_inside_and_outside_range(self):
        a = self.write("a.csv", [("03:00:00", 2000), ("03:15:00", 2000),
                                  ("03:30:00", 2000), ("04:00:00", 2000)])
        b = self.write("b.csv", [("03:15:00", 2000), ("03:45:00", 2000), ("04:00:00", 2000)])
        r = self.compare(a, b)
        self.assertEqual(r["matched_candles"], 2)
        self.assertEqual(len(r["unmatched_left_right"][0]["inside_shared_range"]), 1)
        self.assertEqual(r["unmatched_left_right"][0]["outside_shared_range_count"], 1)

    def test_duplicate_rejected_before_dictionary_can_hide_it(self):
        a = self.write("a.csv", [("03:00:00", 2000)] * 2)
        b = self.write("b.csv", [("03:00:00", 2000)])
        with self.assertRaises(MarketDataError):
            self.compare(a, b)

    def test_no_overlap_rejected(self):
        a = self.write("a.csv", [("03:00:00", 2000)])
        b = self.write("b.csv", [("04:00:00", 2000)])
        with self.assertRaises(MarketDataError):
            self.compare(a, b)

    def test_invalid_threshold_rejected(self):
        for value in ["NaN", "Infinity", "0", "-1"]:
            with self.assertRaises(MarketDataError):
                self.compare(self.root / "missing", self.root / "missing2",
                             threshold=Decimal(value))

    def test_report_hash_and_prices_use_same_snapshot(self):
        a = self.write("a.csv", [("03:00:00", 2006)])
        b = self.write("b.csv", [("03:00:00", 2000)])
        original = a.read_bytes()
        read_bytes = Path.read_bytes

        def read_then_replace(path):
            data = read_bytes(path)
            if path == a:
                self.write("a.csv", [("03:00:00", 3000)])
            return data

        with patch.object(Path, "read_bytes", read_then_replace):
            report = self.compare(a, b)
        self.assertEqual(report["sources"][0]["source_sha256"],
                         hashlib.sha256(original).hexdigest())
        self.assertEqual(report["outliers"][0]["signed_close_difference"], "6")
        self.assertNotEqual(a.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
