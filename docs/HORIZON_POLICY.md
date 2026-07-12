# Forecast horizon and market-reaction policy

IntelliBot treats a market price as the prior, retained evidence as the update, and the published `p_hat` as the final forecast. The analysis audit exposes all three values and never reconstructs them from a later run.

## Deadline horizon

The same deterministic policy is used by the scorer and audit view:

| Days to deadline | Band | Added uncertainty |
| --- | --- | ---: |
| 0–7 | event window | 0.06 |
| >7–45 | near term | 0.03 |
| >45–180 | medium term | 0.01 |
| >180 | long horizon | 0.00 |

The deadline and its provenance come from the parsed market rules, falling back to the linked market expiry. Short horizons widen the interval because timing and final-resolution risk concentrate near the event window.

## Priced-in attribution

For linked binary markets, IntelliBot persists Polymarket CLOB price history for both outcome token IDs. It compares the last YES observation at or before the newest retained evidence timestamp with the latest observation after that timestamp:

- absolute move of at least 0.05: high priced-in risk;
- absolute move of at least 0.02: medium priced-in risk;
- smaller move: low priced-in risk.

The audit records the evidence timestamp, before/after prices, movement, and whether the movement is attributable. When usable price history does not straddle the evidence timestamp, the scorer falls back to the conservative source-age policy and marks the result as non-attributed.
