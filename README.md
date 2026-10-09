# Simple Order Matching Engine


Repository for a simple CLI based order matching engine coding project.

## Running the program

Requires Python 3.11 or later; no third-party dependencies.
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
