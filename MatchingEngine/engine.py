"""Matching engine, built incrementally: storage and order creation first."""

from dataclasses import dataclass
from decimal import Decimal

from .book import BookSide
from .models import (Order, OrderKind, PegReference, Side, Trade,
                     _validate_id, _validate_positive_integer, _validate_price)


@dataclass(frozen=True)
class CommandResult:
    """Individual executions and discarded quantity caused by one command."""

    order_id: str
    trades: tuple[Trade, ...] = ()
    discarded_qty: int = 0

    def aggregated_trades(self) -> tuple[tuple[Decimal, int], ...]:
        totals: dict[Decimal, int] = {}
        for trade in self.trades:
            totals[trade.price] = totals.get(trade.price, 0) + trade.quantity
        return tuple(totals.items())


class MatchingEngine:
    def __init__(self):
        self._buys = BookSide(Side.BUY)
        self._sells = BookSide(Side.SELL)
        self._id_counter = 0
        self._priority_counter = 0
        self._trades: list[Trade] = []
        self._orders: dict[str, Order] = {}
        self._pegs: dict[str, Order] = {}
        self._incoming_id: str | None = None

    @property
    def trade_history(self) -> tuple[Trade, ...]:
        """Expose execution history without allowing callers to change the list."""
        return tuple(self._trades)

    def submit_limit(self, side: Side, price: Decimal, quantity: int) -> CommandResult:
        order = self._create_order(side, OrderKind.LIMIT, quantity, limit_price=price)
        return self._submit(order)

    def submit_market(self, side: Side, quantity: int) -> CommandResult:
        order = self._create_order(side, OrderKind.MARKET, quantity)
        return self._submit(order)

    def submit_peg(self, side: Side, reference: PegReference, quantity: int) -> CommandResult:
        order = self._create_order(side, OrderKind.PEGGED, quantity,
                                   peg_reference=reference)
        self._pegs[order.id] = order
        return self._submit(order)

    def cancel(self, order_id: str) -> CommandResult:
        order = self._require_order(order_id)
        start = len(self._trades)
        if order.effective_price is not None:
            book = self._buys if order.side is Side.BUY else self._sells
            book.remove(order.id)
        self._forget(order)
        self._refresh_pegs()
        self._settle_crossings()
        return CommandResult(order.id, tuple(self._trades[start:]))

    def amend(self, order_id: str, *, quantity: int | None = None,
              price: Decimal | None = None) -> CommandResult:
        """Change remaining quantity/price; increases and new prices lose priority."""
        order = self._require_order(order_id)
        if quantity is None and price is None:
            raise ValueError("provide a quantity or price to amend")
        if quantity is not None:
            _validate_positive_integer(quantity, "quantity")
        if price is not None:
            _validate_price(price)
            if order.kind is not OrderKind.LIMIT:
                raise ValueError("only fixed limit orders allow price amendments")
        # keep old values if not explicitly updated
        new_qty = order.remaining_qty if quantity is None else quantity
        new_price = order.limit_price if price is None else price
        price_changed = new_price != order.limit_price
        start = len(self._trades)
        if not price_changed and new_qty <= order.remaining_qty:
            # Reductions and no-ops leave the order at its existing queue position.
            order.remaining_qty = new_qty
            self._refresh_pegs()
            self._settle_crossings()
            return CommandResult(order.id, tuple(self._trades[start:]))

        book = self._buys if order.side is Side.BUY else self._sells
        if order.effective_price is not None:
            book.remove(order.id)
        self._priority_counter += 1
        order.priority_sequence = self._priority_counter
        order.remaining_qty = new_qty

        if price_changed:
            order.limit_price = new_price
            order.effective_price = new_price
            # Rematch at the new price, then rest any remainder, as on submission.
            return self._submit(order)

        # Quantity increase only: move to the back of the unchanged price queue.
        if order.effective_price is not None:
            book.add(order)
        self._refresh_pegs()
        self._settle_crossings()
        return CommandResult(order.id, tuple(self._trades[start:]))

    def _require_order(self, order_id: str) -> Order:
        """Reject missing or invalid IDs before any state changes."""
        _validate_id(order_id)
        if order_id not in self._orders:
            raise ValueError(f"order {order_id!r} is not active")
        return self._orders[order_id]

    def _forget(self, order: Order) -> None:
        """Remove an order from the outstanding lookup, not from trade history."""
        self._orders.pop(order.id, None)
        self._pegs.pop(order.id, None)

    def _submit(self, order: Order) -> CommandResult:
        start = len(self._trades)
        self._orders[order.id] = order
        self._incoming_id = order.id
        self._refresh_pegs()
        self._match(order)
        discarded = order.remaining_qty if order.kind is OrderKind.MARKET else 0
        self._finish_incoming(order)
        self._incoming_id = None
        self._refresh_pegs()
        self._settle_crossings()
        return CommandResult(order.id, tuple(self._trades[start:]), discarded)

    def _finish_incoming(self, order: Order) -> None:
        """Rest priced remainders; market remainders never enter a book."""
        if order.remaining_qty == 0 or order.kind is OrderKind.MARKET: # discards market remainders
            self._forget(order)
            return
        if order.effective_price is not None:
            book = self._buys if order.side is Side.BUY else self._sells
            book.add(order)

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
                opposite_book.remove(resting.id) # deletes resting order if exhausted
                self._forget(resting)
            if incoming.remaining_qty == 0:
                self._forget(incoming)
            self._refresh_pegs()

    def _refresh_pegs(self) -> None:
        """Move changed pegs as a batch, preserving their previous relative order."""
        references = {
            PegReference.BID: self._buys.fixed_reference(),
            PegReference.OFFER: self._sells.fixed_reference(),
        }
        pegs = sorted(self._pegs.values(), key=lambda order: order.priority_sequence) # preserves previous order
        changes = []
        # First remove all changed pegs, using the same fixed-reference snapshot.
        for order in pegs:
            price = references[order.peg_reference]
            if price == order.effective_price:
                continue
            book = self._buys if order.side is Side.BUY else self._sells
            if book.contains(order.id):
                book.remove(order.id)
            changes.append((order, price))

        # Then append at the new prices, in their old relative priority order.
        for order, price in changes:
            order.effective_price = price
            self._priority_counter += 1
            order.priority_sequence = self._priority_counter
            if price is not None and order.id != self._incoming_id:
                book = self._buys if order.side is Side.BUY else self._sells
                book.add(order)

    def _settle_crossings(self) -> None:
        """Give executable resting pegs matching turns until the book uncrosses."""
        while True:
            buy = self._buys.best()
            sell = self._sells.best()
            if buy is None or sell is None or buy.effective_price < sell.effective_price:
                return

            # A crossing left after an incoming turn must involve at least one peg.
            pegs = [order for order in (buy, sell) if order.kind is OrderKind.PEGGED]
            if not pegs:
                raise RuntimeError("crossed fixed orders violate the engine invariant") # inconsistency
            # One peg takes the incoming role; with two, choose the newer sequence.
            incoming = max(pegs, key=lambda order: order.priority_sequence) # order by priority
            book = self._buys if incoming.side is Side.BUY else self._sells
            book.remove(incoming.id)
            self._incoming_id = incoming.id
            self._match(incoming)
            self._finish_incoming(incoming)
            self._incoming_id = None
            self._refresh_pegs()
