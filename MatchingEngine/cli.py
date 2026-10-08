"""Command parsing and interactive terminal interface."""

from decimal import Decimal, InvalidOperation

from .display import format_book, format_debug_book, format_order, format_trades
from .engine import MatchingEngine
from .models import PegReference, Side


HELP_TEXT = """Commands:
  limit <buy|sell> <price> <quantity>
  market <buy|sell> <quantity>
  peg <bid|offer> <buy|sell> <quantity>
  cancel order <id>
  amend order <id> qty <quantity>
  amend order <id> price <price>
  amend order <id> price <price> qty <quantity>
  print book
  print debug
  show order <id>
  help
  quit

Amendment fields can appear in either order. Quantity means remaining quantity.
Commands are lowercase. Prices are exact internally; normal output uses two decimals."""


def _parse_price(text: str) -> Decimal:
    try:
        return Decimal(text)
    except InvalidOperation as error:
        raise ValueError("price must be a decimal number") from error

# Command examples:
# limit buy 10 100
# market sell 50
# print book

def execute_command(engine: MatchingEngine, line: str) -> str:
    """Parse. Expected input errors propagate to the caller."""
    parts = line.split()
    if not parts:
        return ""
    if parts == ["help"]:
        return HELP_TEXT

    if parts == ["print", "book"]:
        return format_book(engine.book_snapshot())
    if parts == ["print", "debug"]:
        return format_debug_book(engine.debug_snapshot(), engine.inactive_pegs())
    if parts[0] == "show":
        if len(parts) != 3 or parts[1] != "order":
            raise ValueError("usage: show order <id>")
        return format_order(engine.get_order(parts[2]))

    if parts[0] == "limit":
        if len(parts) != 4:
            raise ValueError("usage: limit <buy|sell> <price> <quantity>")
        side = Side(parts[1])
        price = _parse_price(parts[2])
        quantity = int(parts[3])
        result = engine.submit_limit(side, price, quantity)
        confirmation = f"Order created: {result.order_id}"
    elif parts[0] == "market":
        if len(parts) != 3:
            raise ValueError("usage: market <buy|sell> <quantity>")
        side = Side(parts[1])
        quantity = int(parts[2])
        result = engine.submit_market(side, quantity)
        confirmation = f"Order created: {result.order_id}"
    elif parts[0] == "peg":
        if len(parts) != 4:
            raise ValueError("usage: peg <bid|offer> <buy|sell> <quantity>")
        reference = PegReference(parts[1])
        side = Side(parts[2])
        quantity = int(parts[3])
        result = engine.submit_peg(side, reference, quantity)
        confirmation = f"Order created: {result.order_id}"
    elif parts[0] == "cancel":
        if len(parts) != 3 or parts[1] != "order":
            raise ValueError("usage: cancel order <id>")
        result = engine.cancel(parts[2])
        confirmation = f"Order cancelled: {result.order_id}"
    elif parts[0] == "amend":
        if len(parts) not in (5, 7) or parts[1] != "order":
            raise ValueError("usage: amend order <id> <qty|price> <value> [<price|qty> <value>]")
        changes = {}
        for index in range(3, len(parts), 2):
            field = parts[index]
            if field not in ("qty", "price"):
                raise ValueError("amendment fields must be qty or price")
            keyword = "quantity" if field == "qty" else "price"
            if keyword in changes:
                raise ValueError(f"duplicate amendment field: {field}")
            value = parts[index + 1]
            changes[keyword] = int(value) if field == "qty" else _parse_price(value)
        result = engine.amend(parts[2], **changes)
        confirmation = f"Order amended: {result.order_id}"
    else:
        raise ValueError("unknown command; enter help for supported commands")

    lines = [confirmation]
    trades = format_trades(result.aggregated_trades())
    if trades:
        lines.append(trades)
    if result.discarded_qty:
        lines.append(f"Unfilled market quantity discarded: {result.discarded_qty}")
    return "\n".join(lines)


def main() -> None:
    """Keep one engine alive for the session; handle expected input errors only."""
    engine = MatchingEngine()
    print("Matching engine. Enter help for commands, or quit to exit.")
    try:
        while True:
            line = input(">>> ")
            if line.split() == ["quit"]:
                break
            try:
                output = execute_command(engine, line)
            except ValueError as error:
                print(f"Error: {error}")
                continue
            if output:
                print(output)
    except (EOFError, KeyboardInterrupt):
        print()
    print("Closing book engine.")


if __name__ == "__main__":
    main()
