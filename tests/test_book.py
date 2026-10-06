import unittest
from decimal import Decimal

from MatchingEngine.book import BookSide
from MatchingEngine.models import Order, OrderKind, PegReference, Side


class BookTests(unittest.TestCase):
    def order(self, order_id, side, price):
        return Order(order_id, side, OrderKind.LIMIT, 100, int(order_id),
                     limit_price=Decimal(price))

    def test_buy_price_priority_then_fifo(self):
        book = BookSide(Side.BUY)
        for order in (self.order("1", Side.BUY, "10"),
                      self.order("2", Side.BUY, "11"),
                      self.order("3", Side.BUY, "11")):
            book.add(order)
        self.assertEqual(book.best().id, "2")
        self.assertEqual([order.id for order in book.orders()], ["2", "3", "1"])

    def test_sell_lowest_price_first_and_empty_book(self):
        book = BookSide(Side.SELL)
        self.assertIsNone(book.best())
        book.add(self.order("1", Side.SELL, "11"))
        book.add(self.order("2", Side.SELL, "10"))
        self.assertEqual(book.best().id, "2")

    def test_remove_middle_order_preserves_fifo_and_returns_original(self):
        book = BookSide(Side.BUY)
        orders = [self.order(str(i), Side.BUY, "10") for i in (1, 2, 3)]
        for order in orders:
            book.add(order)
        self.assertIs(book.remove("2"), orders[1])
        self.assertEqual([order.id for order in book.orders()], ["1", "3"])
        self.assertIs(book.best(), orders[0])
        book.remove("1")
        self.assertIs(book.best(), orders[2])

    def test_remove_last_order_cleans_level_and_updates_best(self):
        book = BookSide(Side.SELL)
        book.add(self.order("1", Side.SELL, "10"))
        book.add(self.order("2", Side.SELL, "11"))
        book.remove("1")
        self.assertNotIn(Decimal("10"), book._levels)
        self.assertEqual(book.best().id, "2")
        book.remove("2")
        self.assertEqual(book._levels, {})
        self.assertIsNone(book.best())
        self.assertEqual(book.orders(), [])

    def test_remove_unknown_id_leaves_book_unchanged(self):
        book = BookSide(Side.BUY)
        order = self.order("1", Side.BUY, "10")
        book.add(order)
        with self.assertRaisesRegex(ValueError, "not in this book side"):
            book.remove("missing")
        self.assertEqual(book.orders(), [order])
        book.remove("1")
        with self.assertRaises(ValueError):
            book.remove("1")
        self.assertIsNone(book.best())

    def test_location_index_stays_synchronized_when_order_moves(self):
        book = BookSide(Side.BUY)
        order = self.order("1", Side.BUY, "10")
        book.add(order)
        self.assertEqual(book._locations, {"1": Decimal("10")})
        book.remove("1")
        self.assertEqual(book._locations, {})
        order.limit_price = Decimal("11")
        order.effective_price = Decimal("11")
        book.add(order)
        self.assertEqual(book._locations, {"1": Decimal("11")})
        self.assertNotIn(Decimal("10"), book._levels)
        self.assertIs(book.best(), order)

    def test_duplicate_id_at_different_price_does_not_change_index(self):
        book = BookSide(Side.BUY)
        original = self.order("1", Side.BUY, "10")
        book.add(original)
        with self.assertRaises(ValueError):
            book.add(self.order("1", Side.BUY, "11"))
        self.assertEqual(book._locations, {"1": Decimal("10")})
        self.assertEqual(book.orders(), [original])

    def test_fixed_references_choose_highest_bid_and_lowest_offer(self):
        for side, expected in ((Side.BUY, "11"), (Side.SELL, "9")):
            with self.subTest(side=side):
                book = BookSide(side)
                self.assertIsNone(book.fixed_reference())
                for order_id, price in (("1", "10"), ("2", "9"), ("3", "11")):
                    book.add(self.order(order_id, side, price))
                self.assertEqual(book._fixed_prices, list(map(Decimal, ("9", "10", "11"))))
                self.assertEqual(book.fixed_reference(), Decimal(expected))

    def test_last_fixed_removal_clears_reference_even_with_peg_remaining(self):
        book = BookSide(Side.BUY)
        book.add(self.order("1", Side.BUY, "10"))
        book.add(self.order("2", Side.BUY, "10"))
        peg = Order("3", Side.BUY, OrderKind.PEGGED, 100, 3,
                    peg_reference=PegReference.BID, effective_price=Decimal("10"))
        book.add(peg)
        self.assertEqual(book._fixed_counts, {Decimal("10"): 2})
        self.assertEqual(book._fixed_prices, [Decimal("10")])
        book.remove("1")
        self.assertEqual(book._fixed_counts[Decimal("10")], 1)
        self.assertEqual(book.fixed_reference(), Decimal("10"))
        book.remove("2")
        self.assertEqual(book._fixed_counts, {})
        self.assertEqual(book._fixed_prices, [])
        self.assertIsNone(book.fixed_reference())
        self.assertIs(book.best(), peg)  # Book reports references; engine will move pegs.
        book.remove(peg.id)
        self.assertIsNone(book.fixed_reference())

    def test_partial_fill_does_not_change_fixed_order_count(self):
        book = BookSide(Side.SELL)
        order = self.order("1", Side.SELL, "10")
        book.add(order)
        order.remaining_qty = 20
        self.assertEqual(book._fixed_counts[Decimal("10")], 1)
        self.assertEqual(book.fixed_reference(), Decimal("10"))

    def test_moving_fixed_order_updates_reference_indexes(self):
        book = BookSide(Side.BUY)
        order = self.order("1", Side.BUY, "10")
        book.add(order)
        book.remove(order.id)
        order.limit_price = order.effective_price = Decimal("11")
        book.add(order)
        self.assertEqual(book._fixed_counts, {Decimal("11"): 1})
        self.assertEqual(book._fixed_prices, [Decimal("11")])
        self.assertEqual(book.fixed_reference(), Decimal("11"))

    def test_all_price_index_tracks_unique_levels_until_last_order_removed(self):
        book = BookSide(Side.BUY)
        for order_id, price in (("1", "11"), ("2", "9"), ("3", "10"), ("4", "10")):
            book.add(self.order(order_id, Side.BUY, price))
        self.assertEqual(book._prices, list(map(Decimal, ("9", "10", "11"))))
        book.remove("3")
        self.assertEqual(book._prices, list(map(Decimal, ("9", "10", "11"))))
        book.remove("4")
        self.assertEqual(book._prices, list(map(Decimal, ("9", "11"))))
        book.remove("1")
        self.assertEqual(book.best().id, "2")
        book.remove("2")
        self.assertEqual(book._prices, [])
        self.assertIsNone(book.best())

    def test_all_price_index_includes_peg_only_levels(self):
        book = BookSide(Side.SELL)
        peg = Order("1", Side.SELL, OrderKind.PEGGED, 100, 1,
                    peg_reference=PegReference.OFFER, effective_price=Decimal("10"))
        book.add(peg)
        self.assertEqual(book._prices, [Decimal("10")])
        self.assertEqual(book._fixed_prices, [])
        self.assertIs(book.best(), peg)
        self.assertIsNone(book.fixed_reference())
        book.remove(peg.id)
        self.assertEqual(book._prices, [])

    def test_invalid_insertions_leave_book_unchanged(self):
        book = BookSide(Side.BUY)
        valid = self.order("1", Side.BUY, "10")
        book.add(valid)
        for order in (valid, self.order("2", Side.SELL, "10"),
                      Order("3", Side.BUY, OrderKind.MARKET, 100, 3)):
            with self.assertRaises(ValueError):
                book.add(order)
            self.assertEqual(book.orders(), [valid])


if __name__ == "__main__":
    unittest.main()
