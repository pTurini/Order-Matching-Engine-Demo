"""Pure text formatting. No engine mutations or direct printing are done. No state changes."""

from decimal import Decimal
from itertools import zip_longest

from .models import Order, Side


def format_book(snapshot: dict[Side, tuple[tuple[Decimal, int], ...]]) -> str: # receives a book snapshot and prints it
    """Show aggregated levels as independent buy/sell columns."""
    buys = [f"{quantity} @ {price:.2f}" for price, quantity in snapshot[Side.BUY]] # values are rounded to 2 decimal places only in text
    sells = [f"{quantity} @ {price:.2f}" for price, quantity in snapshot[Side.SELL]] # same
    buy_header = "Buy orders"
    sell_header = "Sell orders"
    buy_width = max(len(text) for text in [buy_header, *buys])
    sell_width = max(len(text) for text in [sell_header, *sells])

    lines = [
        f"{buy_header:<{buy_width}} | {sell_header}",
        f"{'-' * buy_width}-+-{'-' * sell_width}",
    ]
    if not buys and not sells:
        lines.append("(empty book)")
    else:
        for buy, sell in zip_longest(buys, sells, fillvalue=""):
            lines.append(f"{buy:<{buy_width}} | {sell}".rstrip())
    return "\n".join(lines)


def format_trades(trades: tuple[tuple[Decimal, int], ...]) -> str:
    """Format already aggregated executions using the required output syntax."""
    return "\n".join(f"Trade, price: {price:.2f}, qty: {quantity}"
                     for price, quantity in trades)


def format_order(order: Order) -> str:
    """Describe one order with exact price and explicit remaining quantity."""
    price = str(order.effective_price) if order.effective_price is not None else "inactive"
    text = (f"ID: {order.id}, side: {order.side.value}, kind: {order.kind.value}, "
            f"remaining qty: {order.remaining_qty}, price: {price}, "
            f"priority: {order.priority_sequence}")
    if order.peg_reference is not None:
        text += f", reference: {order.peg_reference.value}"
    return text


def format_debug_book(snapshot: dict[Side, tuple[Order, ...]],
                      inactive_pegs: tuple[Order, ...]) -> str:
    """List individual orders in supplied queue order, then inactive pegs."""
    lines = []
    for side, heading in ((Side.BUY, "Buy orders (price/FIFO order):"),
                          (Side.SELL, "Sell orders (price/FIFO order):")):
        lines.append(heading)
        if snapshot[side]:
            lines.extend(format_order(order) for order in snapshot[side])
        else:
            lines.append("(none)")
    lines.append("Inactive pegs (priority order):")
    if inactive_pegs:
        lines.extend(format_order(order) for order in inactive_pegs)
    else:
        lines.append("(none)")
    return "\n".join(lines)
