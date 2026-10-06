"""Matching engine, built incrementally: storage and order creation first."""

from decimal import Decimal

from .book import BookSide
from .models import Order, OrderKind, PegReference, Side, Trade


class MatchingEngine:
    def __init__(self):
        self._buys = BookSide(Side.BUY)
        self._sells = BookSide(Side.SELL)
        self._id_counter = 0
        self._priority_counter = 0
        self._trades: list[Trade] = []

    @property
    def trade_history(self) -> tuple[Trade, ...]:
        """Expose execution history without allowing callers to change the list."""
        return tuple(self._trades)

    def _create_order(
        self,
        side: Side,
        kind: OrderKind,
        quantity: int,
        limit_price: Decimal | None = None,
        peg_reference: PegReference | None = None,
    ) -> Order:
        """Create a validated order; do not submit it to either book yet."""
        next_id = self._id_counter + 1
        next_priority = self._priority_counter + 1

        # Order.__post_init__ validates before we change any engine state.
        order = Order(
            id=str(next_id),
            side=side,
            kind=kind,
            remaining_qty=quantity,
            priority_sequence=next_priority,
            limit_price=limit_price,
            peg_reference=peg_reference,
        )

        self._id_counter = next_id
        self._priority_counter = next_priority
        return order

    def _match(self, incoming: Order) -> None:
        """Match until filled or blocked. The incoming order stays outside the book."""
        opposite_book = self._sells if incoming.side is Side.BUY else self._buys
        while incoming.remaining_qty > 0:
            resting = opposite_book.best()
            if resting is None:
                break

            if incoming.kind is not OrderKind.MARKET:
                if incoming.effective_price is None:
                    break
                if incoming.side is Side.BUY and incoming.effective_price < resting.effective_price:
                    break
                if incoming.side is Side.SELL and incoming.effective_price > resting.effective_price:
                    break

            quantity = min(incoming.remaining_qty, resting.remaining_qty)
            buy = incoming if incoming.side is Side.BUY else resting
            sell = resting if incoming.side is Side.BUY else incoming
            trade = Trade(buy.id, sell.id, resting.effective_price, quantity)
            self._trades.append(trade)

            incoming.remaining_qty -= quantity
            resting.remaining_qty -= quantity
            if resting.remaining_qty == 0:
                opposite_book.remove(resting.id)
