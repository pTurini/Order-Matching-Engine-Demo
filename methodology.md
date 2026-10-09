# Methodology:

In this document, I will explain my methodology to solve this problem, as well as the architectural decisions and other assumptions.

## Architecture:

The architecture is divided in 5 main components:
1. Models: contains the classes' structure and validation for all the corresponding data types (order, trade).
2. Book: stores the market orders in the correct order.
3. Engine: contains the logic of the system and the operations that must be done, given a book.
4. CLI: provides interface for the user, and sends the valid commands to the engine.
5. Display: provides functions returning normal/debug book, individual order, and trade text to be fed to the CLI.

## Models:


### Order structure:
| Field | Meaning |
|---|---|
| `id` | Unique submission ID within an engine instance |
| `side` / `kind` | Buy/sell and limit/market/pegged |
| `remaining_qty` | Quantity still available to execute |
| `priority_sequence` | Latest arrival-priority position |
| `limit_price` | Fixed limit price, otherwise absent |
| `peg_reference` | Bid/offer reference for pegs, otherwise absent |
| `effective_price` | Current priced-book value; absent for markets/inactive pegs |

There are also enumerations defined in the Models, respective to the Side of an order (BUY or SELL), the OrderKind (LIMIT, MARKET, PEGGED) and the PegReference (BID, OFFER).
These enums help with readability, validation and separation.

## Book:
The book stores the orders themselves and keep them in price priority. It is used by the matching engine to determine the next executable order.
The book stores queues and indexes to be used by the engine.

| Structure | Contents | Purpose |
|---|---|---|
| `_prices` | Sorted list of every occupied price | Find the best price (best buy last, best sell first) |
| `_levels` | Price -> OrderedDict(ID -> Order) | FIFO at each price plus direct removal |
| `_locations` | ID -> booked price | Find the correct level without scanning |
| `_fixed_counts` | Price -> count of fixed limit orders | Track whether a price can be a peg reference |
| `_fixed_prices` | Sorted prices containing fixed orders | Find the reference for pegged orders |



### Optimization features:
I made some optimizations to make the code run faster, mostly related to lookups. This allows the engine to run faster but has a memory drawback, with the use of extra dictionaries and arrays. This system is rather light-weight, so I assume it should not make a significant difference. However, I think it is nice to have and makes the system more scalable.

`_locations`

## Engine:

### Logic:
* When limit orders cross, the trade is executed at the resting order's price.
* If a market order consumes all available liquidity, the quantity that exceeds that is discarded (does not enter the book).
* Priority is always price first, then arrival time. Price amendment makes an order lose priority.
* Quantity reduction retains priority, quantity increase loses priority in the queue.
* Amending quantities refers to the outstanding quantity (still to be executed).
* Amending but not changing anything does not move the order.
* Amending quantity to zero is rejected. Must be done by the cancel command explicitly. 
* Pegged orders only derive their prices from fixed-price orders.
* When a pegged order arrives with no reference, it waits for a fixed-price order to appear. 
* Pegs are updated after every book changing event, before next match.
* A peg that changes price joins the back of its new price queue (lowest priority).
* Multiple pegs that move together keep their relative order.
* If a peg's updated price crosses, it is executed.
* Pegged order's quantity can be amended, following the same rules as a normal order (decrease keeps priority, increase loses).
* Pegs support buy-to-bid, sell-to-offer, buy-to-offer, sell-to-bid.

### Order logic:
For one incoming order:
1. Find the best order on the opposite side.
2. Check whether its price is acceptable.
3. Execute the smaller remaining quantity.
4. Record the execution at the resting order’s price.
5. Reduce both quantities.
6. Remove any fully filled resting order.
7. Update peg references before choosing the next match.
8. Repeat until the incoming order finishes or cannot match.

The eligibility differs per order type:
- Market: accepts any available price.
- Limit buy: accepts sells at or below its limit.
- Limit sell: accepts buys at or above its limit.
- Peg: uses its current effective price, which could change.

After matching:
- A limit remainder rests.
- A market remainder is discarded.
- A peg remainder rests at its reference price or becomes inactive if no reference exists.

### Design decisions and invalid values:
* On the interface, orders with same price are combined. But internally they have their own IDs and are treated separately.
* Invalid input rejects, gives error message and does nothing to the book.
* Quantity is an integer. No fractional shares.
* Price must be positive and greater than zero.
* Price precision is exact, but interface shows fixed at 0.01 precision.
* Order IDs are unique and never reused within a single session.
* For debugging: show individual orders, remaining quantities, IDs, priority order.




## CLI:

The CLI reads and validates commands inputs from the user, sends to the engine to be executed (if valid), displays the results, and reads the next command.
### Commands:
The available commands are listed below:

| Command | Description |
|---|---|
| `limit <buy\|sell> <price> <quantity>` | Submit a limit order. |
| `market <buy\|sell> <quantity>` | Submit a market order. |
| `peg <bid\|offer> <buy\|sell> <quantity>` | Submit an order pegged to the fixed bid or offer. |
| `cancel order <id>` | Cancel an outstanding order. |
| `amend order <id> qty <quantity>` | Change the remaining quantity. |
| `amend order <id> price <price>` | Change a fixed limit order’s price. |
| `amend order <id> price <price> qty <quantity>` | Change price and remaining quantity; fields may appear in either order. |
| `print book` | Display quantities aggregated by exact price. |
| `print debug` | Display individual orders, priority, exact prices, and inactive pegs. |
| `show order <id>` | Display one outstanding order’s details. |
| `help` | Display command syntax. |
| `quit` | Exit the program. |

Commands are lowercase. Quantities are positive integers and amendments refer to remaining quantity. Prices are exact internally, but normal output displays two decimal places.


## Tests:
Testing was done for each model to check whether its behavior matched expectations. It was particularly important to test the engine's behavior against the assumptions stated in the [Logic](#logic) section.

### Models tests:

* Limit preserves exact price and can be filled.
* All peg combinations can wait without reference.
* Market has no price.
* Invalid quantities and prices are rejected.
* Inconsistent type specific fields are rejected.
* Trade is an immutable individual execution.

### Book tests:

* Buy price priority then FIFO.
* Sell lowest price first and empty book.
* Remove middle order preserves FIFO and returns original.
* Remove last order cleans level and updates best.
* Remove unknown ID leaves book unchanged.
* Location index stays synchronized when order moves.
* Duplicate ID at different price does not change index.
* Fixed references choose highest bid and lowest offer.
* Last fixed removal clears reference even with peg remaining.
* Partial fill does not change fixed order count.
* Moving fixed order updates reference indexes.
* All price index tracks unique levels until last order removed.
* All price index includes peg only levels.
* Invalid insertions leave book unchanged.

### Engine tests:

* Engine starts with two empty books.
* Creation assigns IDs and priority without submitting.
* Invalid creation does not change counters or books.
* Buy executes at resting price and leaves resting remainder.
* Sell selects best bid and removes fully filled order.
* Same price FIFO and market has no price boundary.
* Non crossing limits leave quantities unchanged.
* Equal limit price is eligible and filled incoming cannot repeat.
* Empty book and unpriced peg do not execute.
* Buy sweeps prices then stops at limit.
* History accumulates across orders and returns snapshot.
* Passive limits rest on correct side.
* Crossing limit rests remainder at its limit.
* Market discards remainder and never rests.
* Email example aggregation and command history boundaries.
* Limit stops before ineligible level and exact prices stay separate.
* Invalid submission leaves books history and counters unchanged.
* Cancel middle order preserves other orders and counters.
* Cancel partially filled sell preserves trade history.
* Completed orders and market remainders leave lookup.
* Limit remainder remains registered and can be cancelled.
* Invalid and repeated cancellation leave state unchanged.
* Reduction and no-op preserve priority on both sides.
* Increase moves to back and execution respects new priority.
* Amended quantity means remaining after partial fill.
* Invalid quantity and inactive ID leave state unchanged.
* New price repositions behind existing orders and keeps id.
* Crossing price amendment returns only new trades and rests remainder.
* Sell price change can fill completely and clean lookup.
* Same price is no-op but changed price with reduction loses priority.
* All fields are validated before any change.
* Primary pegs join behind fixed orders on both sides.
* All combinations wait without reference and can be cancelled.
* Opposite side pegs execute and completed pegs leave registries.
* Resting peg cleanup when filled and manual price rejected.
* Invalid peg submission does not advance counters.
* Multiple pegs move behind new fixed order in previous order.
* Peg waits deactivates and reactivates.
* Reference updates before market next fill.
* Incoming opposite peg follows each reference and waits with remainder.
* Unchanged reference preserves peg priority on quantity increase.
* Price amendment moves peg to new fixed reference.
* Waiting buy offer executes when fixed offer appears.
* Multiple waiting pegs execute FIFO on both sides.
* Repeated reference activation reports new trades only.
* Aggressive incoming peg can fill resting primary peg.
* Mixed commands leave consistent uncrossed books and conserve quantity.
* Active pegged quantity amendments preserve or lose FIFO.
* Sell bid peg sweeps changing references and retains remainder.
* Repricing uses current queue order after peg quantity increase.
* Order inspection returns copy that cannot change live state.
* Inspected copy is a snapshot and inactive pegs are accessible.
* Unknown invalid cancelled and completed orders cannot be inspected.
* Aggregated snapshot uses remaining quantity exact prices and best order.
* Debug snapshot preserves FIFO and copies live orders.
* Inactive pegs are separate detached and ordered.
* Snapshots do not change after later execution.

### CLI tests:

* Limit market and book share engine state.
* Crossing limit and aggregated trade output.
* Exact prices whitespace blank input and trade format.
* Peg commands support all combinations and follow on trades.
* Cancel command removes outstanding order.
* Amend commands accept either field order and report crossing trades.
* Invalid new commands are atomic.
* Show and debug preserve exact prices remaining quantity and FIFO.
* Empty debug and invalid inspection commands.
* Invalid commands leave engine state unchanged.
* Session reuses engine recovers from error and quits.
* EOF and keyboard interrupt exit cleanly.
* Help and quit require exact syntax.
* Unexpected programming errors are not hidden.
* Book is redrawn above latest command and error.
* Screen clears only when output is a terminal.

### Display tests:

* Two columns keep snapshot order and handle unequal lengths.
* Empty and single sided books.
* Rounding is display only and does not merge exact levels.
* Large values keep separator aligned.

## Extras(if time allows):

### Market-making:



### Simulation:
