import random
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


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.engine = MatchingEngine()

    def test_passive_limits_rest_on_correct_side(self):
        buy = self.engine.submit_limit(Side.BUY, Decimal("10"), 100)
        sell = self.engine.submit_limit(Side.SELL, Decimal("11"), 200)
        self.assertEqual((buy.order_id, sell.order_id), ("1", "2"))
        self.assertEqual(buy.trades, ())
        self.assertEqual(sell.trades, ())
        self.assertEqual(self.engine._buys.best().remaining_qty, 100)
        self.assertEqual(self.engine._sells.best().remaining_qty, 200)

    def test_crossing_limit_rests_remainder_at_its_limit(self):
        sell = self.engine.submit_limit(Side.SELL, Decimal("10"), 100)
        buy = self.engine.submit_limit(Side.BUY, Decimal("11"), 150)
        self.assertEqual((buy.trades[0].price, buy.trades[0].quantity), (Decimal("10"), 100))
        self.assertEqual(buy.trades[0].sell_order_id, sell.order_id)
        self.assertEqual(buy.discarded_qty, 0)
        self.assertIsNone(self.engine._sells.best())
        remainder = self.engine._buys.best()
        self.assertEqual((remainder.id, remainder.effective_price, remainder.remaining_qty),
                         (buy.order_id, Decimal("11"), 50))

    def test_market_discards_remainder_and_never_rests(self):
        self.engine.submit_limit(Side.BUY, Decimal("10"), 100)
        result = self.engine.submit_market(Side.SELL, 150)
        self.assertEqual(result.discarded_qty, 50)
        self.assertEqual(result.trades[0].quantity, 100)
        self.assertIsNone(self.engine._buys.best())
        self.assertIsNone(self.engine._sells.best())
        empty = self.engine.submit_market(Side.BUY, 20)
        self.assertEqual((empty.trades, empty.discarded_qty), ((), 20))

    def test_email_example_aggregation_and_command_history_boundaries(self):
        self.engine.submit_limit(Side.BUY, Decimal("10"), 100)
        first = self.engine.submit_limit(Side.SELL, Decimal("20"), 100)
        second = self.engine.submit_limit(Side.SELL, Decimal("20"), 200)
        result = self.engine.submit_market(Side.BUY, 150)
        self.assertEqual([(t.sell_order_id, t.quantity) for t in result.trades],
                         [(first.order_id, 100), (second.order_id, 50)])
        self.assertEqual(result.aggregated_trades(), ((Decimal("20"), 150),))
        next_result = self.engine.submit_market(Side.BUY, 200)
        self.assertEqual(len(next_result.trades), 1)
        self.assertEqual(next_result.aggregated_trades(), ((Decimal("20"), 150),))
        self.assertEqual(next_result.discarded_qty, 50)
        last = self.engine.submit_market(Side.SELL, 200)
        self.assertEqual(last.aggregated_trades(), ((Decimal("10"), 100),))
        self.assertEqual(last.discarded_qty, 100)
        self.assertEqual(len(result.trades), 2)  # Earlier result is unchanged.
        self.assertEqual(len(self.engine.trade_history), 4)

    def test_limit_stops_before_ineligible_level_and_exact_prices_stay_separate(self):
        self.engine.submit_limit(Side.SELL, Decimal("10.001"), 10)
        self.engine.submit_limit(Side.SELL, Decimal("10.002"), 10)
        self.engine.submit_limit(Side.SELL, Decimal("11"), 10)
        result = self.engine.submit_limit(Side.BUY, Decimal("10.5"), 30)
        self.assertEqual(result.aggregated_trades(),
                         ((Decimal("10.001"), 10), (Decimal("10.002"), 10)))
        self.assertEqual(self.engine._buys.best().remaining_qty, 10)
        self.assertEqual(self.engine._sells.best().effective_price, Decimal("11"))

    def test_invalid_submission_leaves_books_history_and_counters_unchanged(self):
        self.engine.submit_limit(Side.SELL, Decimal("10"), 100)
        before = (self.engine._buys.orders(), self.engine._sells.orders(),
                  self.engine.trade_history, self.engine._id_counter, self.engine._priority_counter)
        for submit in (
            lambda: self.engine.submit_limit(Side.BUY, Decimal("11"), 0),
            lambda: self.engine.submit_limit(Side.BUY, 11.0, 50),
            lambda: self.engine.submit_limit(Side.BUY, Decimal("NaN"), 50),
            lambda: self.engine.submit_market("buy", 50),
            lambda: self.engine.submit_market(Side.BUY, True),
        ):
            with self.assertRaises(ValueError):
                submit()
            after = (self.engine._buys.orders(), self.engine._sells.orders(),
                     self.engine.trade_history, self.engine._id_counter, self.engine._priority_counter)
            self.assertEqual(after, before)
        self.assertEqual(self.engine._sells.best().remaining_qty, 100)


class CancellationTests(unittest.TestCase):
    def setUp(self):
        self.engine = MatchingEngine()

    def test_cancel_middle_order_preserves_other_orders_and_counters(self):
        results = [self.engine.submit_limit(Side.BUY, Decimal("10"), 100)
                   for _ in range(3)]
        counters = (self.engine._id_counter, self.engine._priority_counter)
        result = self.engine.cancel(results[1].order_id)
        self.assertEqual((result.order_id, result.trades, result.discarded_qty),
                         (results[1].order_id, (), 0))
        expected = [results[0].order_id, results[2].order_id]
        self.assertEqual([order.id for order in self.engine._buys.orders()], expected)
        self.assertEqual(list(self.engine._orders), expected)
        self.assertEqual((self.engine._id_counter, self.engine._priority_counter), counters)

    def test_cancel_partially_filled_sell_preserves_trade_history(self):
        result = self.engine.submit_limit(Side.SELL, Decimal("10"), 100)
        live = self.engine._orders[result.order_id]
        self.assertIs(live, self.engine._sells.best())
        self.engine.submit_market(Side.BUY, 40)
        self.assertEqual(live.remaining_qty, 60)
        history = self.engine.trade_history
        self.engine.cancel(result.order_id)
        self.assertEqual(self.engine._orders, {})
        self.assertIsNone(self.engine._sells.best())
        self.assertEqual(self.engine.trade_history, history)
        next_order = self.engine.submit_limit(Side.SELL, Decimal("10"), 100)
        self.assertNotEqual(next_order.order_id, result.order_id)

    def test_completed_orders_and_market_remainders_leave_lookup(self):
        sell = self.engine.submit_limit(Side.SELL, Decimal("10"), 100)
        buy = self.engine.submit_limit(Side.BUY, Decimal("11"), 100)
        self.assertEqual(self.engine._orders, {})
        market = self.engine.submit_market(Side.BUY, 50)
        self.assertEqual(market.discarded_qty, 50)
        self.assertEqual(self.engine._orders, {})
        for order_id in (sell.order_id, buy.order_id, market.order_id):
            with self.assertRaisesRegex(ValueError, "not active"):
                self.engine.cancel(order_id)

    def test_limit_remainder_remains_registered_and_can_be_cancelled(self):
        self.engine.submit_limit(Side.SELL, Decimal("10"), 100)
        result = self.engine.submit_limit(Side.BUY, Decimal("11"), 150)
        self.assertEqual(list(self.engine._orders), [result.order_id])
        self.assertEqual(self.engine._orders[result.order_id].remaining_qty, 50)
        self.engine.cancel(result.order_id)
        self.assertEqual(self.engine._orders, {})
        self.assertIsNone(self.engine._buys.best())

    def test_invalid_and_repeated_cancellation_leave_state_unchanged(self):
        result = self.engine.submit_limit(Side.BUY, Decimal("10"), 100)
        order = self.engine._orders[result.order_id]
        for invalid in ("missing", "", None, [], 1):
            with self.assertRaises(ValueError):
                self.engine.cancel(invalid)
            self.assertIs(self.engine._orders[result.order_id], order)
            self.assertIs(self.engine._buys.best(), order)
            self.assertEqual(order.remaining_qty, 100)
            self.assertEqual(self.engine.trade_history, ())
        self.engine.cancel(result.order_id)
        with self.assertRaises(ValueError):
            self.engine.cancel(result.order_id)
        self.assertEqual(self.engine._orders, {})
        self.assertIsNone(self.engine._buys.best())


class QuantityAmendmentTests(unittest.TestCase):
    def setUp(self):
        self.engine = MatchingEngine()

    def test_reduction_and_noop_preserve_priority_on_both_sides(self):
        for side in Side:
            with self.subTest(side=side):
                engine = MatchingEngine()
                first = engine.submit_limit(side, Decimal("10"), 100)
                second = engine.submit_limit(side, Decimal("10"), 100)
                order = engine._orders[first.order_id]
                priority = order.priority_sequence
                counters = (engine._id_counter, engine._priority_counter)
                result = engine.amend(first.order_id, quantity=50)
                engine.amend(first.order_id, quantity=50)
                book = engine._buys if side is Side.BUY else engine._sells
                self.assertEqual([o.id for o in book.orders()], [first.order_id, second.order_id])
                self.assertEqual(order.remaining_qty, 50)
                self.assertEqual(order.priority_sequence, priority)
                self.assertEqual((engine._id_counter, engine._priority_counter), counters)
                self.assertEqual((result.order_id, result.trades, result.discarded_qty),
                                 (first.order_id, (), 0))

    def test_increase_moves_to_back_and_execution_respects_new_priority(self):
        first = self.engine.submit_limit(Side.SELL, Decimal("10"), 100)
        second = self.engine.submit_limit(Side.SELL, Decimal("10"), 100)
        live = self.engine._orders[first.order_id]
        self.engine.amend(first.order_id, quantity=150)
        self.assertEqual([o.id for o in self.engine._sells.orders()],
                         [second.order_id, first.order_id])
        self.assertIs(self.engine._orders[first.order_id], live)
        self.assertEqual(live.priority_sequence, 3)
        self.assertEqual(self.engine._id_counter, 2)
        result = self.engine.submit_market(Side.BUY, 120)
        self.assertEqual([(t.sell_order_id, t.quantity) for t in result.trades],
                         [(second.order_id, 100), (first.order_id, 20)])
        self.assertEqual(live.remaining_qty, 130)

    def test_amended_quantity_means_remaining_after_partial_fill(self):
        created = self.engine.submit_limit(Side.BUY, Decimal("10"), 100)
        self.engine.submit_market(Side.SELL, 40)
        history = self.engine.trade_history
        self.engine.amend(created.order_id, quantity=80)
        self.assertEqual(self.engine._orders[created.order_id].remaining_qty, 80)
        self.assertEqual(self.engine.trade_history, history)
        result = self.engine.submit_market(Side.SELL, 100)
        self.assertEqual(result.trades[0].quantity, 80)
        self.assertEqual(result.discarded_qty, 20)

    def test_invalid_quantity_and_inactive_id_leave_state_unchanged(self):
        created = self.engine.submit_limit(Side.BUY, Decimal("10"), 100)
        order = self.engine._orders[created.order_id]
        counters = (self.engine._id_counter, self.engine._priority_counter)
        priority = order.priority_sequence
        for quantity in (0, -1, 1.5, True, None, "100"):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.engine.amend(created.order_id, quantity=quantity)
            self.assertEqual(order.remaining_qty, 100)
            self.assertEqual(order.priority_sequence, priority)
            self.assertIs(self.engine._buys.best(), order)
            self.assertEqual((self.engine._id_counter, self.engine._priority_counter), counters)
            self.assertEqual(self.engine.trade_history, ())
        with self.assertRaises(ValueError):
            self.engine.amend("missing", quantity=150)
        self.assertEqual(order.remaining_qty, 100)
        self.engine.cancel(created.order_id)
        with self.assertRaises(ValueError):
            self.engine.amend(created.order_id, quantity=150)
        self.assertEqual(self.engine._orders, {})


class PriceAmendmentTests(unittest.TestCase):
    def setUp(self):
        self.engine = MatchingEngine()

    def test_new_price_repositions_behind_existing_orders_and_keeps_id(self):
        first = self.engine.submit_limit(Side.BUY, Decimal("10"), 200)
        second = self.engine.submit_limit(Side.BUY, Decimal("9.99"), 100)
        live = self.engine._orders[first.order_id]
        result = self.engine.amend(first.order_id, price=Decimal("9.99"))
        self.assertEqual([o.id for o in self.engine._buys.orders()],
                         [second.order_id, first.order_id])
        self.assertIs(self.engine._orders[first.order_id], live)
        self.assertEqual((live.limit_price, live.effective_price),
                         (Decimal("9.99"), Decimal("9.99")))
        self.assertEqual(live.priority_sequence, 3)
        self.assertEqual(self.engine._id_counter, 2)
        self.assertEqual(result.trades, ())
        self.engine.amend(first.order_id, price=Decimal("9.98"))
        self.assertEqual([o.effective_price for o in self.engine._buys.orders()],
                         [Decimal("9.99"), Decimal("9.98")])

    def test_crossing_price_amendment_returns_only_new_trades_and_rests_remainder(self):
        buy = self.engine.submit_limit(Side.BUY, Decimal("9"), 100)
        self.engine.submit_market(Side.SELL, 40)
        sell = self.engine.submit_limit(Side.SELL, Decimal("10"), 50)
        result = self.engine.amend(buy.order_id, price=Decimal("11"), quantity=80)
        self.assertEqual(len(result.trades), 1)
        self.assertEqual((result.trades[0].price, result.trades[0].quantity),
                         (Decimal("10"), 50))
        self.assertEqual(result.trades[0].sell_order_id, sell.order_id)
        self.assertEqual(self.engine._orders[buy.order_id].remaining_qty, 30)
        self.assertEqual(self.engine._buys.best().effective_price, Decimal("11"))
        self.assertEqual(len(self.engine.trade_history), 2)
        self.assertEqual(result.discarded_qty, 0)

    def test_sell_price_change_can_fill_completely_and_clean_lookup(self):
        sell = self.engine.submit_limit(Side.SELL, Decimal("12"), 50)
        self.engine.submit_limit(Side.BUY, Decimal("10"), 50)
        result = self.engine.amend(sell.order_id, price=Decimal("9"))
        self.assertEqual(result.trades[0].price, Decimal("10"))
        self.assertEqual(result.trades[0].quantity, 50)
        self.assertEqual(self.engine._orders, {})
        self.assertIsNone(self.engine._sells.best())
        self.assertIsNone(self.engine._buys.best())

    def test_same_price_is_noop_but_changed_price_with_reduction_loses_priority(self):
        first = self.engine.submit_limit(Side.SELL, Decimal("12"), 100)
        second = self.engine.submit_limit(Side.SELL, Decimal("11"), 100)
        order = self.engine._orders[first.order_id]
        priority = order.priority_sequence
        self.engine.amend(first.order_id, price=Decimal("12.00"))
        self.assertEqual(order.priority_sequence, priority)
        self.engine.amend(first.order_id, price=Decimal("11"), quantity=50)
        self.assertEqual(order.remaining_qty, 50)
        self.assertGreater(order.priority_sequence, priority)
        self.assertEqual([o.id for o in self.engine._sells.orders()],
                         [second.order_id, first.order_id])

    def test_all_fields_are_validated_before_any_change(self):
        result = self.engine.submit_limit(Side.BUY, Decimal("10"), 100)
        order = self.engine._orders[result.order_id]
        for fields in ({"price": Decimal("NaN"), "quantity": 150},
                       {"price": Decimal("-1")}, {"price": 11.0},
                       {"price": Decimal("11"), "quantity": 0}, {}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.engine.amend(result.order_id, **fields)
            self.assertEqual((order.limit_price, order.effective_price, order.remaining_qty,
                              order.priority_sequence), (Decimal("10"), Decimal("10"), 100, 1))
            self.assertIs(self.engine._buys.best(), order)
            self.assertEqual((self.engine._id_counter, self.engine._priority_counter), (1, 1))
            self.assertEqual(self.engine.trade_history, ())


class PegPlacementTests(unittest.TestCase):
    def setUp(self):
        self.engine = MatchingEngine()

    def test_primary_pegs_join_behind_fixed_orders_on_both_sides(self):
        for side, reference in ((Side.BUY, PegReference.BID),
                                (Side.SELL, PegReference.OFFER)):
            with self.subTest(side=side):
                engine = MatchingEngine()
                fixed = engine.submit_limit(side, Decimal("10"), 100)
                result = engine.submit_peg(side, reference, 50)
                book = engine._buys if side is Side.BUY else engine._sells
                self.assertEqual([o.id for o in book.orders()], [fixed.order_id, result.order_id])
                peg = engine._orders[result.order_id]
                self.assertIs(engine._pegs[result.order_id], peg)
                self.assertEqual(peg.effective_price, Decimal("10"))
                self.assertIsNone(peg.limit_price)
                self.assertEqual(result.trades, ())

    def test_all_combinations_wait_without_reference_and_can_be_cancelled(self):
        for side in Side:
            for reference in PegReference:
                with self.subTest(side=side, reference=reference):
                    engine = MatchingEngine()
                    result = engine.submit_peg(side, reference, 50)
                    self.assertIsNone(engine._orders[result.order_id].effective_price)
                    self.assertIn(result.order_id, engine._pegs)
                    self.assertEqual(engine._buys.orders(), [])
                    self.assertEqual(engine._sells.orders(), [])
                    engine.amend(result.order_id, quantity=80)
                    self.assertEqual(engine._pegs[result.order_id].remaining_qty, 80)
                    engine.cancel(result.order_id)
                    self.assertEqual(engine._orders, {})
                    self.assertEqual(engine._pegs, {})

    def test_opposite_side_pegs_execute_and_completed_pegs_leave_registries(self):
        for side, reference, resting_side in (
            (Side.BUY, PegReference.OFFER, Side.SELL),
            (Side.SELL, PegReference.BID, Side.BUY),
        ):
            with self.subTest(side=side):
                engine = MatchingEngine()
                fixed = engine.submit_limit(resting_side, Decimal("10"), 100)
                result = engine.submit_peg(side, reference, 40)
                self.assertEqual((result.trades[0].price, result.trades[0].quantity),
                                 (Decimal("10"), 40))
                self.assertNotIn(result.order_id, engine._orders)
                self.assertNotIn(result.order_id, engine._pegs)
                self.assertEqual(engine._orders[fixed.order_id].remaining_qty, 60)

    def test_resting_peg_cleanup_when_filled_and_manual_price_rejected(self):
        fixed = self.engine.submit_limit(Side.BUY, Decimal("10"), 100)
        result = self.engine.submit_peg(Side.BUY, PegReference.BID, 50)
        peg = self.engine._pegs[result.order_id]
        priority = peg.priority_sequence
        with self.assertRaises(ValueError):
            self.engine.amend(result.order_id, price=Decimal("11"), quantity=80)
        self.assertEqual((peg.remaining_qty, peg.effective_price, peg.priority_sequence),
                         (50, Decimal("10"), priority))
        # Increasing the fixed order puts it behind the peg without changing price.
        self.engine.amend(fixed.order_id, quantity=150)
        self.engine.submit_market(Side.SELL, 200)
        self.assertEqual(self.engine._pegs, {})
        self.assertEqual(self.engine._orders, {})

    def test_invalid_peg_submission_does_not_advance_counters(self):
        for side, reference, quantity in ((Side.BUY, "bid", 50),
                                          ("buy", PegReference.BID, 50),
                                          (Side.BUY, PegReference.BID, 0)):
            with self.assertRaises(ValueError):
                self.engine.submit_peg(side, reference, quantity)
            self.assertEqual(self.engine._pegs, {})
            self.assertEqual(self.engine._orders, {})
            self.assertEqual((self.engine._id_counter, self.engine._priority_counter), (0, 0))


class PegRepricingTests(unittest.TestCase):
    def setUp(self):
        self.engine = MatchingEngine()

    def test_multiple_pegs_move_behind_new_fixed_order_in_previous_order(self):
        old = self.engine.submit_limit(Side.BUY, Decimal("10"), 100)
        p = self.engine.submit_peg(Side.BUY, PegReference.BID, 50)
        q = self.engine.submit_peg(Side.BUY, PegReference.BID, 60)
        new = self.engine.submit_limit(Side.BUY, Decimal("11"), 100)
        self.assertEqual([o.id for o in self.engine._buys.orders()],
                         [new.order_id, p.order_id, q.order_id, old.order_id])
        self.engine.cancel(new.order_id)
        self.assertEqual([o.id for o in self.engine._buys.orders()],
                         [old.order_id, p.order_id, q.order_id])
        self.assertEqual(self.engine._pegs[p.order_id].effective_price, Decimal("10"))

    def test_peg_waits_deactivates_and_reactivates(self):
        p = self.engine.submit_peg(Side.SELL, PegReference.OFFER, 50)
        fixed = self.engine.submit_limit(Side.SELL, Decimal("10"), 100)
        self.assertEqual([o.id for o in self.engine._sells.orders()], [fixed.order_id, p.order_id])
        self.engine.cancel(fixed.order_id)
        self.assertIsNone(self.engine._pegs[p.order_id].effective_price)
        self.assertEqual(self.engine._sells.orders(), [])
        self.assertIn(p.order_id, self.engine._orders)
        new = self.engine.submit_limit(Side.SELL, Decimal("11"), 100)
        self.assertEqual([o.id for o in self.engine._sells.orders()], [new.order_id, p.order_id])
        self.assertEqual(self.engine._pegs[p.order_id].effective_price, Decimal("11"))

    def test_reference_updates_before_market_next_fill(self):
        self.engine.submit_limit(Side.BUY, Decimal("10"), 100)
        p = self.engine.submit_peg(Side.BUY, PegReference.BID, 100)
        lower = self.engine.submit_limit(Side.BUY, Decimal("9"), 100)
        result = self.engine.submit_market(Side.SELL, 150)
        self.assertEqual([(t.price, t.quantity) for t in result.trades],
                         [(Decimal("10"), 100), (Decimal("9"), 50)])
        self.assertEqual(result.trades[1].buy_order_id, lower.order_id)
        self.assertEqual(self.engine._pegs[p.order_id].effective_price, Decimal("9"))

    def test_incoming_opposite_peg_follows_each_reference_and_waits_with_remainder(self):
        self.engine.submit_limit(Side.SELL, Decimal("10"), 100)
        self.engine.submit_limit(Side.SELL, Decimal("11"), 100)
        result = self.engine.submit_peg(Side.BUY, PegReference.OFFER, 250)
        self.assertEqual([(t.price, t.quantity) for t in result.trades],
                         [(Decimal("10"), 100), (Decimal("11"), 100)])
        self.assertEqual(self.engine._pegs[result.order_id].remaining_qty, 50)
        self.assertIsNone(self.engine._pegs[result.order_id].effective_price)
        self.assertEqual(self.engine._buys.orders(), [])

    def test_unchanged_reference_preserves_peg_priority_on_quantity_increase(self):
        fixed = self.engine.submit_limit(Side.BUY, Decimal("10"), 100)
        p = self.engine.submit_peg(Side.BUY, PegReference.BID, 50)
        sequence = self.engine._pegs[p.order_id].priority_sequence
        self.engine.amend(fixed.order_id, quantity=150)
        self.assertEqual(self.engine._pegs[p.order_id].priority_sequence, sequence)
        self.assertEqual([o.id for o in self.engine._buys.orders()], [p.order_id, fixed.order_id])

    def test_price_amendment_moves_peg_to_new_fixed_reference(self):
        fixed = self.engine.submit_limit(Side.SELL, Decimal("11"), 100)
        p = self.engine.submit_peg(Side.SELL, PegReference.OFFER, 50)
        self.engine.amend(fixed.order_id, price=Decimal("10"))
        self.assertEqual(self.engine._pegs[p.order_id].effective_price, Decimal("10"))
        self.assertEqual([o.id for o in self.engine._sells.orders()], [fixed.order_id, p.order_id])


class PegSettlementTests(unittest.TestCase):
    def test_waiting_buy_offer_executes_when_fixed_offer_appears(self):
        engine = MatchingEngine()
        peg = engine.submit_peg(Side.BUY, PegReference.OFFER, 150)
        result = engine.submit_limit(Side.SELL, Decimal("10.50"), 100)
        self.assertEqual([(t.buy_order_id, t.sell_order_id, t.price, t.quantity)
                          for t in result.trades],
                         [(peg.order_id, result.order_id, Decimal("10.50"), 100)])
        self.assertEqual(engine._pegs[peg.order_id].remaining_qty, 50)
        self.assertIsNone(engine._pegs[peg.order_id].effective_price)
        self.assertEqual(engine._buys.orders(), [])
        self.assertEqual(engine._sells.orders(), [])
        self.assertIsNone(engine._incoming_id)

    def test_multiple_waiting_pegs_execute_fifo_on_both_sides(self):
        for side, ref, opposite in ((Side.BUY, PegReference.OFFER, Side.SELL),
                                    (Side.SELL, PegReference.BID, Side.BUY)):
            with self.subTest(side=side):
                engine = MatchingEngine()
                p = engine.submit_peg(side, ref, 100)
                q = engine.submit_peg(side, ref, 100)
                result = engine.submit_limit(opposite, Decimal("10"), 150)
                ids = [t.buy_order_id if side is Side.BUY else t.sell_order_id
                       for t in result.trades]
                self.assertEqual(ids, [p.order_id, q.order_id])
                self.assertEqual([t.quantity for t in result.trades], [100, 50])
                self.assertEqual(result.aggregated_trades(), ((Decimal("10"), 150),))
                self.assertNotIn(p.order_id, engine._orders)
                self.assertEqual(engine._pegs[q.order_id].remaining_qty, 50)
                self.assertIsNone(engine._pegs[q.order_id].effective_price)

    def test_repeated_reference_activation_reports_new_trades_only(self):
        engine = MatchingEngine()
        fixed = engine.submit_limit(Side.SELL, Decimal("12"), 100)
        engine.submit_limit(Side.BUY, Decimal("10"), 50)
        peg = engine.submit_peg(Side.SELL, PegReference.BID, 100)
        # Peg fills the fixed bid, then waits with 50. Amendment rests a new bid.
        self.assertEqual(engine._pegs[peg.order_id].remaining_qty, 50)
        new_buy = engine.submit_limit(Side.BUY, Decimal("9"), 20)
        self.assertEqual(new_buy.trades[0].sell_order_id, peg.order_id)
        # With offers removed, a new offer-pegged buyer waits for the next sell.
        engine.cancel(fixed.order_id)
        waiting = engine.submit_peg(Side.BUY, PegReference.OFFER, 40)
        sell = engine.submit_limit(Side.SELL, Decimal("11"), 100)
        self.assertEqual(sell.trades[0].buy_order_id, waiting.order_id)
        amended = engine.amend(sell.order_id, price=Decimal("10"))
        self.assertEqual(amended.trades, ())
        self.assertEqual(engine._sells.best().effective_price, Decimal("10"))

    def test_aggressive_incoming_peg_can_fill_resting_primary_peg(self):
        engine = MatchingEngine()
        fixed = engine.submit_limit(Side.SELL, Decimal("10"), 100)
        primary = engine.submit_peg(Side.SELL, PegReference.OFFER, 50)
        engine.amend(fixed.order_id, quantity=150)  # Primary now precedes fixed.
        # Two opposing pegs participate when a new aggressive peg arrives.
        aggressive = engine.submit_peg(Side.BUY, PegReference.OFFER, 70)
        self.assertEqual([(t.sell_order_id, t.quantity) for t in aggressive.trades],
                         [(primary.order_id, 50), (fixed.order_id, 20)])
        self.assertEqual([t.price for t in aggressive.trades], [Decimal("10"), Decimal("10")])
        self.assertNotIn(primary.order_id, engine._pegs)

    def test_mixed_commands_leave_consistent_uncrossed_books_and_conserve_quantity(self):
        rng = random.Random(42)
        engine = MatchingEngine()
        total = executed = discarded = cancelled = 0
        for _ in range(400):
            action = rng.randrange(5)
            side = rng.choice(list(Side))
            qty = rng.randrange(1, 30)
            active = list(engine._orders)
            if action < 3 or not active:
                total += qty
                if action == 0:
                    result = engine.submit_market(side, qty)
                elif action == 1:
                    result = engine.submit_peg(side, rng.choice(list(PegReference)), qty)
                else:
                    result = engine.submit_limit(side, Decimal(rng.randrange(8, 14)), qty)
            elif action == 3:
                order_id = rng.choice(active)
                cancelled += engine._orders[order_id].remaining_qty
                result = engine.cancel(order_id)
            else:
                order_id = rng.choice(active)
                order = engine._orders[order_id]
                total += qty - order.remaining_qty
                price = Decimal(rng.randrange(8, 14)) if order.kind is OrderKind.LIMIT else None
                result = engine.amend(order_id, quantity=qty, price=price)
            executed += 2 * sum(t.quantity for t in result.trades)
            discarded += result.discarded_qty
            remaining = sum(order.remaining_qty for order in engine._orders.values())
            self.assertEqual(total, executed + discarded + cancelled + remaining)
            self.assertEqual(sum(t.quantity for t in engine.trade_history) * 2, executed)
            self.assertIsNone(engine._incoming_id)
            buy, sell = engine._buys.best(), engine._sells.best()
            if buy and sell:
                self.assertLess(buy.effective_price, sell.effective_price)
            for book in (engine._buys, engine._sells):
                self.assertEqual(book._prices, sorted(book._levels))
                for queue in book._levels.values():
                    sequences = [o.priority_sequence for o in queue.values()]
                    self.assertEqual(sequences, sorted(sequences))
                    for order in queue.values():
                        self.assertIs(engine._orders[order.id], order)
                        self.assertGreater(order.remaining_qty, 0)
                fixed_counts = {}
                for order in book.orders():
                    if order.kind is OrderKind.LIMIT:
                        price = order.effective_price
                        fixed_counts[price] = fixed_counts.get(price, 0) + 1
                self.assertEqual(book._fixed_counts, fixed_counts)
                self.assertEqual(book._fixed_prices, sorted(fixed_counts))
            for peg in engine._pegs.values():
                reference = engine._buys if peg.peg_reference is PegReference.BID else engine._sells
                self.assertEqual(peg.effective_price, reference.fixed_reference())
                book = engine._buys if peg.side is Side.BUY else engine._sells
                self.assertEqual(book.contains(peg.id), peg.effective_price is not None)


if __name__ == "__main__":
    unittest.main()
