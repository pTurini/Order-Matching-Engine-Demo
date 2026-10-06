# Methodology:

In this document, I will explain my methodology to solve this problem, as well as the architectural decisions and other assumptions.

## Architecture:

The architecture is divided in 4 mains components:
1. Models: contains the classes' structure and validation for all the corresponding data types (order, trade).
2. Book: stores the market orders in the correct order.
3. Engine: contains the logic of the system and the operations that must be done, given a book.
4. CLI: provides interface for the user.

### Functions:
Create, match, amend, or cancel orders.
Update quantities and remove completed orders.
Update affected pegged orders.


### Order structure:
| Field | Function |
|---|---|
| `id` | Unique identifier|
| `side` | Buy/sell |
| `kind` | Limit / pegged  |
| `remaining_qty` | Quantity still available |
| `limit_price` | Fixed price for a limit order |
| `peg_reference` | Bid or offer for a pegged order |
| `effective_price` | Current book price; absent for an inactive peg |
| `priority_sequence` | Increasing number identifying its latest queue position |

## Assumptions:

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

### Interface and general rules:
* On the interface, orders with same price are combined. But internally they have their own IDs and are treated separately.
* Invalid input rejects, gives error message and does nothing to the book.
* Quantity is an integer. No fractional shares.\
* Price must be positive and greater than zero.
* Price precision is exact, but interface shows fixed at 0.01 precision.
* Order IDs are unique and never reused.
* For debugging: show individual orders, remaining quantities, IDs, priority order.

## Tests:
Test ideas:
* Best-price matching and FIFO.
* Partial fills and market remainder disposal.
* Crossing limits with resting-price execution.
* Cancellation after a partial fill.
* Amendment priority changes and invalid zero quantities.
* Peg movement after submission, cancellation, amendment, and execution.
* Multiple pegs repricing together.
* Opposite-side pegs consuming several reference levels.
* Missing references and reactivation.
* Invalid commands leaving the state unchanged.

### Models tests:
* Exact limit prices and quantity reaching zero after a fill.
* All four peg combinations waiting without a reference.
* Market orders having no price.
* Invalid quantities and prices.
* Inconsistent type-specific fields.
* Immutable, individual trade records.



## Extras(if time allows):

### Market-making:



### Simulation:
