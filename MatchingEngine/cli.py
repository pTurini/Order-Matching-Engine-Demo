"""Parse one command and return output text; the interactive loop comes later."""

from decimal import Decimal, InvalidOperation

from .display import format_book, format_trades
from .engine import MatchingEngine
from .models import Side


def execute_command(engine: MatchingEngine, line: str) -> str:
    """Parse. Expected input errors propagate to the caller."""
    parts = line.split()
    if not parts:
        return ""

    if parts == ["print", "book"]:
        return format_book(engine.book_snapshot())

    if parts[0] == "limit":
        if len(parts) != 4:
            raise ValueError("usage: limit <buy|sell> <price> <quantity>")
        side = Side(parts[1])
        try:
            price = Decimal(parts[2])
        except InvalidOperation as error:
            raise ValueError("price must be a decimal number") from error
        quantity = int(parts[3])
        result = engine.submit_limit(side, price, quantity)
    elif parts[0] == "market":
        if len(parts) != 3:
            raise ValueError("usage: market <buy|sell> <quantity>")
        side = Side(parts[1])
        quantity = int(parts[2])
        result = engine.submit_market(side, quantity)
    else:
        raise ValueError("unknown command; supported: limit, market, print book")

    lines = [f"Order created: {result.order_id}"]
    trades = format_trades(result.aggregated_trades())
    if trades:
        lines.append(trades)
    if result.discarded_qty:
        lines.append(f"Unfilled market quantity discarded: {result.discarded_qty}")
    return "\n".join(lines)
