import unittest
from decimal import Decimal

from MatchingEngine.book import BookSide
from MatchingEngine.models import Order, OrderKind, Side


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
