# Order-Matching-Engine-Demo


A simple CLI-based, in-memory order matching engine for one asset. Supports limit,
market, and pegged orders, price-time priority, partial fills, cancellation, and amendments.

See the [methodology](methodology.md) for the architecture, implementation details,
trading rules, assumptions, and testing approach. It documents the project and explains the reasoning behind my design decisions.

## Running the program

Requires Python 3.11 or later, with no third-party dependencies.
From this directory (`Order-Matching-Engine-Demo`), run:

```powershell
python -m MatchingEngine.cli
```

Enter `help` for command syntax and `quit` to exit. For example:

```text
limit buy 10 100
limit sell 20 100
limit sell 20 200
market buy 150
print book
print debug
quit
```

The engine stays in memory for the session. Restarting starts a new empty book.
Invalid commands print an error without changing the book. EOF and Ctrl+C exit
cleanly. Run tests with `python -m unittest discover -s tests -v`.

## Commands

```text
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
```

Commands are all lowercase. 

Replace placeholders such as `<id>` with the actual values.
Order submissions return an ID that can be used for inspection, cancellation, or amendment.

Quantities are positive integers. Amendments change the remaining quantity, and
quantity and price fields may appear in either order. Manual price amendments
apply only to fixed limit orders. Use cancellation to remove an order rather than
amending its quantity to zero.

Pegged orders follow the best fixed bid or offer and wait outside the book when
their reference is unavailable. All four side/reference combinations are supported by this implementation.

`print book` shows quantities aggregated by exact price, while `print debug` shows
individual orders, IDs, priority sequences, exact prices, and inactive pegs.
`show order <id>` displays one outstanding order. 

Prices are exact internally, but normal output uses two decimal places.
