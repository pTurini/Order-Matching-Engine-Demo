"""Order book storage, built incrementally."""

from collections import OrderedDict
from decimal import Decimal

from .models import Order, OrderKind, Side


class BookSide:
    """One side of the book: prices containing queues of individual orders."""

    def __init__(self, side: Side):
        if not isinstance(side, Side):
            raise ValueError("side must be a Side")
        self.side = side
        self._levels: dict[Decimal, OrderedDict[str, Order]] = {}
        self._locations: dict[str, Decimal] = {}

    def add(self, order: Order) -> None:
        if order.side is not self.side:
            raise ValueError("order belongs to the other side")
        if order.kind is OrderKind.MARKET or order.effective_price is None:
            raise ValueError("only priced limit or pegged orders can rest")
        if order.remaining_qty <= 0:
            raise ValueError("a resting order must have remaining quantity")
        if order.id in self._locations:
            raise ValueError("order ID is already in this book side")

        price = order.effective_price
        if price not in self._levels:
            self._levels[price] = OrderedDict()
        self._levels[price][order.id] = order
        self._locations[order.id] = price

    def remove(self, order_id: str) -> Order:
        """Remove an individual order, preserving the queue order."""
        if order_id not in self._locations:
            raise ValueError(f"order {order_id!r} is not in this book side")
        price = self._locations.pop(order_id)
        queue = self._levels[price]
        order = queue.pop(order_id)
        if not queue:
            del self._levels[price]
        return order

    def best(self) -> Order | None:
        if not self._levels:
            return None
        if self.side is Side.BUY:
            price = max(self._levels)
        else:
            price = min(self._levels)
        return next(iter(self._levels[price].values()))

    def orders(self) -> list[Order]:
        """Return individual orders in best-price order, FIFO within each price."""
        prices = sorted(self._levels, reverse=self.side is Side.BUY)
        result = []
        for price in prices:
            result.extend(self._levels[price].values())
        return result
