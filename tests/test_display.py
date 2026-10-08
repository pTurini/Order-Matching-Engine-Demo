import unittest
from decimal import Decimal

from MatchingEngine.display import format_book
from MatchingEngine.engine import MatchingEngine
from MatchingEngine.models import Side


class BookDisplayTests(unittest.TestCase):
    def test_two_columns_keep_snapshot_order_and_handle_unequal_lengths(self):
        snapshot = {
            Side.BUY: ((Decimal("10"), 150), (Decimal("9.99"), 100)),
            Side.SELL: ((Decimal("11"), 200),),
        }
        self.assertEqual(format_book(snapshot),
                         "Buy orders  | Sell orders\n"
                         "------------+------------\n"
                         "150 @ 10.00 | 200 @ 11.00\n"
                         "100 @ 9.99  |")

    def test_empty_and_single_sided_books(self):
        empty = {Side.BUY: (), Side.SELL: ()}
        self.assertIn("(empty book)", format_book(empty))
        sell_only = {Side.BUY: (), Side.SELL: ((Decimal("10"), 50),)}
        self.assertEqual(format_book(sell_only).splitlines()[-1], "           | 50 @ 10.00")

    def test_rounding_is_display_only_and_does_not_merge_exact_levels(self):
        engine = MatchingEngine()
        engine.submit_limit(Side.BUY, Decimal("10.001"), 100)
        engine.submit_limit(Side.BUY, Decimal("10.002"), 50)
        snapshot = engine.book_snapshot()
        before = engine.debug_snapshot()
        output = format_book(snapshot)
        self.assertIn("50 @ 10.00", output)
        self.assertIn("100 @ 10.00", output)
        self.assertEqual(len(output.splitlines()), 4)
        self.assertEqual(engine.debug_snapshot(), before)
        self.assertEqual(engine.book_snapshot(), snapshot)

    def test_large_values_keep_separator_aligned(self):
        snapshot = {
            Side.BUY: ((Decimal("123456.78"), 1000000),),
            Side.SELL: ((Decimal("234567.89"), 2000000),),
        }
        lines = format_book(snapshot).splitlines()
        self.assertEqual(lines[0].index("|"), lines[2].index("|"))
        self.assertEqual(lines[1].index("+"), lines[2].index("|"))


if __name__ == "__main__":
    unittest.main()
