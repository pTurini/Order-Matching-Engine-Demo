import unittest
from decimal import Decimal

from MatchingEngine.cli import execute_command
from MatchingEngine.display import format_trades
from MatchingEngine.engine import MatchingEngine
from MatchingEngine.models import Side


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.engine = MatchingEngine()

    def test_limit_market_and_book_share_engine_state(self):
        self.assertEqual(execute_command(self.engine, "limit sell 10 100"), "Order created: 1")
        self.assertEqual(execute_command(self.engine, "market buy 150"),
                         "Order created: 2\nTrade, price: 10.00, qty: 100\n"
                         "Unfilled market quantity discarded: 50")
        self.assertIn("(empty book)", execute_command(self.engine, "print book"))

    def test_crossing_limit_and_aggregated_trade_output(self):
        execute_command(self.engine, "limit sell 10 100")
        execute_command(self.engine, "limit sell 10 200")
        self.assertEqual(execute_command(self.engine, "limit buy 11 150"),
                         "Order created: 3\nTrade, price: 10.00, qty: 150")
        self.assertEqual(len(self.engine.trade_history), 2)
        self.assertIn("150 @ 10.00", execute_command(self.engine, "print book"))

    def test_exact_prices_whitespace_blank_input_and_trade_format(self):
        execute_command(self.engine, "  limit   buy  10.001  100  ")
        self.assertEqual(self.engine.book_snapshot()[Side.BUY], ((Decimal("10.001"), 100),))
        self.assertEqual(execute_command(self.engine, "   "), "")
        self.assertEqual(format_trades(()), "")
        self.assertEqual(format_trades(((Decimal("10.001"), 100), (Decimal("10.002"), 50))),
                         "Trade, price: 10.00, qty: 100\nTrade, price: 10.00, qty: 50")

    def test_peg_commands_support_all_combinations_and_follow_on_trades(self):
        for reference in ("bid", "offer"):
            for side in ("buy", "sell"):
                engine = MatchingEngine()
                self.assertEqual(execute_command(engine, f"peg {reference} {side} 50"),
                                 "Order created: 1")
                self.assertIsNone(engine.get_order("1").effective_price)
        execute_command(self.engine, "peg offer buy 50")
        self.assertEqual(execute_command(self.engine, "limit sell 10 100"),
                         "Order created: 2\nTrade, price: 10.00, qty: 50")

    def test_cancel_command_removes_outstanding_order(self):
        execute_command(self.engine, "limit buy 10 100")
        self.assertEqual(execute_command(self.engine, "cancel order 1"), "Order cancelled: 1")
        self.assertIn("(empty book)", execute_command(self.engine, "print book"))

    def test_amend_commands_accept_either_field_order_and_report_crossing_trades(self):
        execute_command(self.engine, "limit buy 9 100")
        execute_command(self.engine, "limit sell 10 50")
        self.assertEqual(execute_command(self.engine, "amend order 1 qty 80 price 11"),
                         "Order amended: 1\nTrade, price: 10.00, qty: 50")
        self.assertEqual(self.engine.get_order("1").remaining_qty, 30)
        execute_command(self.engine, "amend order 1 price 10.5 qty 20")
        self.assertEqual(self.engine.get_order("1").limit_price, Decimal("10.5"))
        execute_command(self.engine, "amend order 1 qty 10")
        execute_command(self.engine, "amend order 1 price 10")
        self.assertEqual(self.engine.get_order("1").remaining_qty, 10)

    def test_invalid_new_commands_are_atomic(self):
        execute_command(self.engine, "limit buy 10 100")
        execute_command(self.engine, "peg bid buy 50")
        before = (self.engine.debug_snapshot(), self.engine.inactive_pegs(),
                  self.engine.trade_history, self.engine._id_counter, self.engine._priority_counter)
        for command in ("peg bid buy", "peg wrong buy 10", "peg bid wrong 10",
                        "peg bid buy 0", "cancel 1", "cancel order 1 extra",
                        "cancel order missing", "amend order 1", "amend order 1 qty",
                        "amend order 1 qty 20 qty 30", "amend order 1 price 11 price 12",
                        "amend order 1 qty 20 unknown 30", "amend order 1 qty 20 price bad",
                        "amend order 1 qty 0 price 11", "amend order 2 price 11"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                execute_command(self.engine, command)
            after = (self.engine.debug_snapshot(), self.engine.inactive_pegs(),
                     self.engine.trade_history, self.engine._id_counter, self.engine._priority_counter)
            self.assertEqual(after, before)

    def test_invalid_commands_leave_engine_state_unchanged(self):
        execute_command(self.engine, "limit sell 10 100")
        before = (self.engine.debug_snapshot(), self.engine.trade_history,
                  self.engine._id_counter, self.engine._priority_counter)
        for command in ("limit buy 11", "limit buy 11 50 extra", "limit wrong 11 50",
                        "limit buy bad 50", "limit buy 11 1.5", "limit buy NaN 50",
                        "market buy", "market buy 0", "market buy -1",
                        "market buy 50 extra", "print book extra", "unknown"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                execute_command(self.engine, command)
            after = (self.engine.debug_snapshot(), self.engine.trade_history,
                     self.engine._id_counter, self.engine._priority_counter)
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
