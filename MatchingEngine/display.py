"""Pure text formatting. No engine mutations or direct printing are done. No state changes."""

from decimal import Decimal
from itertools import zip_longest

from .models import Side


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
