import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal

from MatchingEngine.models import Order, OrderKind, PegReference, Side, Trade


class ModelTests(unittest.TestCase):
    def test_limit_preserves_exact_price_and_can_be_filled(self):
        order = Order("1", Side.BUY, OrderKind.LIMIT, 100, 1,
                      limit_price=Decimal("10.005"))
        self.assertEqual(order.effective_price, Decimal("10.005"))
        order.remaining_qty = 0
        self.assertEqual(order.remaining_qty, 0)

    def test_all_peg_combinations_can_wait_without_reference(self):
        for side in Side:
            for reference in PegReference:
                with self.subTest(side=side, reference=reference):
                    order = Order("1", side, OrderKind.PEGGED, 100, 1,
                                  peg_reference=reference)
                    self.assertIsNone(order.effective_price)

    def test_market_has_no_price(self):
        order = Order("1", Side.SELL, OrderKind.MARKET, 100, 1)
        self.assertIsNone(order.effective_price)
        with self.assertRaises(ValueError):
            Order("2", Side.SELL, OrderKind.MARKET, 100, 2,
                  limit_price=Decimal("10"))

    def test_invalid_quantities_and_prices_are_rejected(self):
        for qty in (0, -1, 1.5, True):
            with self.subTest(qty=qty), self.assertRaises(ValueError):
                Order("1", Side.BUY, OrderKind.MARKET, qty, 1)
        for price in (None, 10.0, Decimal("0"), Decimal("-1"),
                      Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(price=price), self.assertRaises(ValueError):
                Order("1", Side.BUY, OrderKind.LIMIT, 100, 1,
                      limit_price=price)

    def test_inconsistent_type_specific_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            Order("1", Side.BUY, OrderKind.PEGGED, 100, 1)
        with self.assertRaises(ValueError):
            Order("1", Side.BUY, OrderKind.LIMIT, 100, 1,
                  limit_price=Decimal("10"), effective_price=Decimal("11"))
        with self.assertRaises(ValueError):
            Order("1", Side.BUY, OrderKind.PEGGED, 100, 1,
                  limit_price=Decimal("10"), peg_reference=PegReference.BID)

    def test_trade_is_an_immutable_individual_execution(self):
        trade = Trade("buy-1", "sell-1", Decimal("10.005"), 50)
        self.assertEqual(trade.price, Decimal("10.005"))
        with self.assertRaises(FrozenInstanceError):
            trade.quantity = 100
        with self.assertRaises(ValueError):
            Trade("same", "same", Decimal("10"), 50)


if __name__ == "__main__":
    unittest.main()
