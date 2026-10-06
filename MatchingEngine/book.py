"""Order book storage, built incrementally."""

from decimal import Decimal

from .models import Order, OrderKind, Side


class BookSide:
    """One side of the book: prices containing queues of individual orders."""

    def __init__(self, side: Side):
        if not isinstance(side, Side):
            raise ValueError("side must be a Side")
        self.side = side
        self._levels: dict[Decimal, list[Order]] = {}

    def add(self, order: Order) -> None:
        if order.side is not self.side:
            raise ValueError("order belongs to the other side")
        if order.kind is OrderKind.MARKET or order.effective_price is None:
            raise ValueError("only priced limit or pegged orders can rest")
        if order.remaining_qty <= 0:
            raise ValueError("a resting order must have remaining quantity")
        if any(existing.id == order.id for existing in self.orders()):
            raise ValueError("order ID is already in this book side")

        price = order.effective_price
        if price not in self._levels:
            self._levels[price] = []
        self._levels[price].append(order)

    def best(self) -> Order | None:
        if not self._levels:
            return None
        if self.side is Side.BUY:
            price = max(self._levels)
        else:
            price = min(self._levels)
        return self._levels[price][0]

    def orders(self) -> list[Order]:
        """Return individual orders in best-price order, FIFO within each price."""
        prices = sorted(self._levels, reverse=self.side is Side.BUY)
        result = []
        for price in prices:
            result.extend(self._levels[price])
        return result
