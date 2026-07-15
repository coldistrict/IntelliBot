# Blind Model Read

## What it is

Every run records `blind_p_hat`: the model's probability that the question
resolves YES, produced from only the resolution conditions, the deadline, and
the verified evidence lines — never the market price. The prompt builder takes
no market object at all, and the instruction explicitly tells the model to
disregard any odds mentioned inside evidence text.

## Why it exists

The headline forecast is `p_hat = sigmoid(logit(market_mid) + capped_evidence)`
— a deliberate market-prior update. Measured on 2026-07-15 (10 linked runs,
historical + fresh batch), the evidence term ranged 0.02–0.25 logits while a
lean recommendation needs roughly 0.75+, so `p_hat` structurally cannot
disagree with the market enough to surface an edge (0 leans in 48 scored runs;
median |p_hat − mid| ≈ 2 pts). The blind read is the independent signal that
CAN disagree; the scoreboard's fifth Brier view ("Model · blind read") will
show over resolved markets whether that disagreement carries information.

## Guarantees

- Recorded in the execution ledger like any model call (cost, tokens,
  latency, result_mode).
- Auxiliary only: it never feeds `p_hat`, the recommendation, uncertainty, or
  edge math, and its failure never degrades run quality
  (`AUXILIARY_TASKS` in `analysis_execution.py`); the run simply stores NULL.
- Published immutably on `published_forecasts.blind_p_hat` and scored in
  calibration only when the market resolves.

## How to interpret

Compare the three numbers on any linked run: market prior, desk `p_hat`
(anchored posterior), and the blind read. A persistent, calibrated gap between
the blind read and the market on resolved questions is the precondition for
ever trusting desk-vs-market disagreement with money. Until the fifth view
accumulates resolved samples, treat the blind read as instrumentation, not
signal.
