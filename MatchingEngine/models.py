"""Order state and execution records, independent of matching and display."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

# Possible values for each field 
class Side(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderKind(Enum):
    LIMIT = "limit"
    MARKET = "market"
    PEGGED = "pegged"


class PegReference(Enum):
    BID = "bid"
    OFFER = "offer"


# Validation functions
def _validate_positive_integer(value: int, name: str) -> None:
    # bool is an int subclass, but is not a valid quantity or sequence.
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _validate_price(value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError("price must be a positive, finite Decimal")


def _validate_id(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("order ID must be a nonempty string")

# Order class
@dataclass
class Order:
    """Mutable state owned by the engine.

    IDs and priority sequences are assigned by the engine. A new sequence is
    assigned whenever an order loses priority. Market orders are transient and
    never rest in the book. A pegged order with no effective price is inactive.

    Validation runs at construction; the engine must validate amendments before
    mutating state. Zero remaining quantity is valid after a complete fill, but
    cannot be submitted as an initial quantity or amendment.
    """

    id: str
    side: Side
    kind: OrderKind
    remaining_qty: int
    priority_sequence: int
    limit_price: Decimal | None = None
    peg_reference: PegReference | None = None
    effective_price: Decimal | None = None

    def __post_init__(self) -> None:
        _validate_id(self.id)
        if not isinstance(self.side, Side):
            raise ValueError("side must be a Side")
        if not isinstance(self.kind, OrderKind):
            raise ValueError("kind must be an OrderKind")
        _validate_positive_integer(self.remaining_qty, "quantity")
        _validate_positive_integer(self.priority_sequence, "priority sequence")

        if self.kind is OrderKind.LIMIT:
            _validate_price(self.limit_price)
            if self.peg_reference is not None:
                raise ValueError("limit orders cannot have a peg reference")
            if self.effective_price is not None and self.effective_price != self.limit_price:
                raise ValueError("limit effective price must equal its limit price")
            if self.effective_price is not None:
                _validate_price(self.effective_price)
            self.effective_price = self.limit_price
        elif self.kind is OrderKind.MARKET:
            if any(value is not None for value in
                   (self.limit_price, self.peg_reference, self.effective_price)):
                raise ValueError("market orders cannot have a price or peg reference")
        else:
            if self.limit_price is not None:
                raise ValueError("pegged orders cannot have a fixed limit price")
            if not isinstance(self.peg_reference, PegReference):
                raise ValueError("pegged orders require a PegReference")
            if self.effective_price is not None:
                _validate_price(self.effective_price)

# Trade class
@dataclass(frozen=True)
class Trade:
    """One execution between two orders."""

    buy_order_id: str
    sell_order_id: str
    price: Decimal
    quantity: int

    def __post_init__(self) -> None:
        _validate_id(self.buy_order_id)
        _validate_id(self.sell_order_id)
        if self.buy_order_id == self.sell_order_id:
            raise ValueError("a trade must involve two distinct orders")
        _validate_price(self.price)
        _validate_positive_integer(self.quantity, "trade quantity")
