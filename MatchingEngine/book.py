"""Order book storage, built incrementally."""

from bisect import bisect_left, insort
from collections import OrderedDict
from decimal import Decimal

from .models import Order, OrderKind, Side


class BookSide:
    """One side of the book: prices containing queues of individual orders."""

    def __init__(self, side: Side):
        if not isinstance(side, Side):
            raise ValueError("side must be a Side")
        self.side = side
        self._prices: list[Decimal] = []  # All occupied prices, ascending.
        self._levels: dict[Decimal, OrderedDict[str, Order]] = {}
        self._locations: dict[str, Decimal] = {}
        self._fixed_counts: dict[Decimal, int] = {}
        self._fixed_prices: list[Decimal] = []

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
            insort(self._prices, price)
            self._levels[price] = OrderedDict()
        self._levels[price][order.id] = order
        self._locations[order.id] = price
        if order.kind is OrderKind.LIMIT:
            if price not in self._fixed_counts:
                self._fixed_counts[price] = 0
                insort(self._fixed_prices, price)
            self._fixed_counts[price] += 1

    def remove(self, order_id: str) -> Order:
        """Remove an individual order, preserving the queue order."""
        if order_id not in self._locations:
            raise ValueError(f"order {order_id!r} is not in this book side")
        price = self._locations.pop(order_id)
        queue = self._levels[price]
        order = queue.pop(order_id)
        if order.kind is OrderKind.LIMIT:
            self._fixed_counts[price] -= 1
            if self._fixed_counts[price] == 0:
                del self._fixed_counts[price]
                index = bisect_left(self._fixed_prices, price)
                self._fixed_prices.pop(index)
        if not queue:
            del self._levels[price]
            index = bisect_left(self._prices, price)
            self._prices.pop(index)
        return order

    def best(self) -> Order | None:
        if not self._prices:
            return None
        if self.side is Side.BUY:
            price = self._prices[-1]
        else:
            price = self._prices[0]
        return next(iter(self._levels[price].values()))

    def fixed_reference(self) -> Decimal | None:
        """Return the best fixed limit price, excluding every pegged order."""
        if not self._fixed_prices:
            return None
        if self.side is Side.BUY:
            return self._fixed_prices[-1]
        return self._fixed_prices[0]

    def orders(self) -> list[Order]:
        """Return individual orders in best-price order, FIFO within each price."""
        prices = reversed(self._prices) if self.side is Side.BUY else self._prices
        result = []
        for price in prices:
            result.extend(self._levels[price].values())
        return result
