import unittest
from decimal import Decimal

from MatchingEngine.engine import MatchingEngine
from MatchingEngine.models import OrderKind, PegReference, Side


class EngineCreationTests(unittest.TestCase):
    def test_engine_starts_with_two_empty_books(self):
        engine = MatchingEngine()
        self.assertIs(engine._buys.side, Side.BUY)
        self.assertIs(engine._sells.side, Side.SELL)
        self.assertEqual(engine._buys.orders(), [])
        self.assertEqual(engine._sells.orders(), [])

    def test_creation_assigns_ids_and_priority_without_submitting(self):
        engine = MatchingEngine()
        limit = engine._create_order(Side.BUY, OrderKind.LIMIT, 100,
                                     limit_price=Decimal("10.005"))
        market = engine._create_order(Side.SELL, OrderKind.MARKET, 50)
        peg = engine._create_order(Side.BUY, OrderKind.PEGGED, 25,
                                   peg_reference=PegReference.OFFER)
        self.assertEqual([order.id for order in (limit, market, peg)], ["1", "2", "3"])
        self.assertEqual([order.priority_sequence for order in (limit, market, peg)],
                         [1, 2, 3])
        self.assertEqual(limit.effective_price, Decimal("10.005"))
        self.assertIsNone(market.effective_price)
        self.assertIsNone(peg.effective_price)
        self.assertEqual(engine._buys.orders(), [])
        self.assertEqual(engine._sells.orders(), [])

    def test_invalid_creation_does_not_change_counters_or_books(self):
        engine = MatchingEngine()
        with self.assertRaises(ValueError):
            engine._create_order(Side.BUY, OrderKind.LIMIT, 0,
                                 limit_price=Decimal("10"))
        self.assertEqual(engine._id_counter, 0)
        self.assertEqual(engine._priority_counter, 0)
        self.assertEqual(engine._buys.orders(), [])
        self.assertEqual(engine._sells.orders(), [])
        valid = engine._create_order(Side.BUY, OrderKind.MARKET, 100)
        self.assertEqual(valid.id, "1")
        self.assertEqual(valid.priority_sequence, 1)


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.engine = MatchingEngine()

    def limit(self, side, price, quantity):
        return self.engine._create_order(side, OrderKind.LIMIT, quantity,
                                         limit_price=Decimal(price))

    def test_buy_executes_at_resting_price_and_leaves_resting_remainder(self):
        resting = self.limit(Side.SELL, "10.005", 100)
        self.engine._sells.add(resting)
        incoming = self.limit(Side.BUY, "11", 40)
        self.engine._match(incoming)
        trade = self.engine.trade_history[0]
        self.assertEqual((trade.buy_order_id, trade.sell_order_id), (incoming.id, resting.id))
        self.assertEqual((trade.price, trade.quantity), (Decimal("10.005"), 40))
        self.assertEqual(incoming.remaining_qty, 0)
        self.assertEqual(resting.remaining_qty, 60)
        self.assertIs(self.engine._sells.best(), resting)

    def test_sell_selects_best_bid_and_removes_fully_filled_order(self):
        low = self.limit(Side.BUY, "9", 100)
        high = self.limit(Side.BUY, "10", 50)
        self.engine._buys.add(low)
        self.engine._buys.add(high)
        incoming = self.limit(Side.SELL, "8", 80)
        self.engine._match(incoming)
        trade = self.engine.trade_history[0]
        self.assertEqual((trade.price, trade.quantity), (Decimal("10"), 50))
        self.assertEqual((trade.buy_order_id, trade.sell_order_id), (high.id, incoming.id))
        self.assertEqual(incoming.remaining_qty, 0)
        self.assertIs(self.engine._buys.best(), low)
        self.assertEqual(low.remaining_qty, 70)
        self.assertEqual([(t.price, t.quantity) for t in self.engine.trade_history],
                         [(Decimal("10"), 50), (Decimal("9"), 30)])

    def test_same_price_fifo_and_market_has_no_price_boundary(self):
        first = self.limit(Side.SELL, "20", 10)
        second = self.limit(Side.SELL, "20", 20)
        self.engine._sells.add(first)
        self.engine._sells.add(second)
        incoming = self.engine._create_order(Side.BUY, OrderKind.MARKET, 15)
        self.engine._match(incoming)
        trade = self.engine.trade_history[0]
        self.assertEqual((trade.sell_order_id, trade.quantity), (first.id, 10))
        self.assertEqual(incoming.remaining_qty, 0)
        self.assertEqual(second.remaining_qty, 15)
        self.assertEqual([(t.sell_order_id, t.quantity) for t in self.engine.trade_history],
                         [(first.id, 10), (second.id, 5)])

    def test_non_crossing_limits_leave_quantities_unchanged(self):
        for side, resting_price, incoming_price in (
            (Side.BUY, "11", "10"), (Side.SELL, "10", "11")
        ):
            with self.subTest(side=side):
                self.engine = MatchingEngine()
                opposite = Side.SELL if side is Side.BUY else Side.BUY
                resting = self.limit(opposite, resting_price, 100)
                book = self.engine._sells if side is Side.BUY else self.engine._buys
                book.add(resting)
                incoming = self.limit(side, incoming_price, 50)
                self.engine._match(incoming)
                self.assertEqual(self.engine.trade_history, ())
                self.assertEqual((incoming.remaining_qty, resting.remaining_qty), (50, 100))

    def test_equal_limit_price_is_eligible_and_filled_incoming_cannot_repeat(self):
        resting = self.limit(Side.SELL, "10", 100)
        self.engine._sells.add(resting)
        incoming = self.limit(Side.BUY, "10", 50)
        self.engine._match(incoming)
        self.assertEqual(self.engine.trade_history[0].quantity, 50)
        self.engine._match(incoming)
        self.assertEqual(len(self.engine.trade_history), 1)
        self.assertEqual(resting.remaining_qty, 50)

    def test_empty_book_and_unpriced_peg_do_not_execute(self):
        market = self.engine._create_order(Side.BUY, OrderKind.MARKET, 50)
        self.engine._match(market)
        self.assertEqual(self.engine.trade_history, ())
        self.assertEqual(market.remaining_qty, 50)
        resting = self.limit(Side.SELL, "10", 100)
        self.engine._sells.add(resting)
        peg = self.engine._create_order(Side.BUY, OrderKind.PEGGED, 50,
                                        peg_reference=PegReference.BID)
        self.engine._match(peg)
        self.assertEqual(self.engine.trade_history, ())
        self.assertEqual((peg.remaining_qty, resting.remaining_qty), (50, 100))

    def test_buy_sweeps_prices_then_stops_at_limit(self):
        for price in ("12", "10", "11"):
            self.engine._sells.add(self.limit(Side.SELL, price, 10))
        incoming = self.limit(Side.BUY, "11", 30)
        self.engine._match(incoming)
        self.assertEqual([(t.price, t.quantity) for t in self.engine.trade_history],
                         [(Decimal("10"), 10), (Decimal("11"), 10)])
        self.assertEqual(incoming.remaining_qty, 10)
        self.assertEqual(self.engine._sells.best().effective_price, Decimal("12"))
        self.assertEqual(self.engine._buys.orders(), [])  # Remainder handling comes later.

    def test_history_accumulates_across_orders_and_returns_snapshot(self):
        self.engine._sells.add(self.limit(Side.SELL, "10", 100))
        first = self.engine._create_order(Side.BUY, OrderKind.MARKET, 40)
        self.engine._match(first)
        snapshot = self.engine.trade_history
        second = self.engine._create_order(Side.BUY, OrderKind.MARKET, 100)
        self.engine._match(second)
        self.assertEqual([t.quantity for t in self.engine.trade_history], [40, 60])
        self.assertEqual(len(snapshot), 1)
        self.assertIsInstance(snapshot, tuple)
        self.assertEqual(second.remaining_qty, 40)
        self.assertIsNone(self.engine._sells.best())


if __name__ == "__main__":
    unittest.main()
