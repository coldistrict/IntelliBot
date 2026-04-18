# Manual Analysis Strategy

This document explains how the current codebase handles a manual analysis request from submission to memo output.

It is based on the code paths in:

- `frontend/components/analysis/manual-analysis-form.tsx`
- `backend/app/api/routes/analyses.py`
- `backend/app/schemas/analysis.py`
- `backend/app/services/analysis_pipeline.py`
- `backend/app/services/analysis_scoring.py`
- `backend/app/services/analysis_progress.py`
- `backend/app/services/analysis_presentation.py`
- `backend/app/services/analysis_audit.py`

## 1. What manual analysis is

Manual analysis is the workflow for questions that a user composes directly rather than waiting for an automatic scan.

The code accepts exactly one primary input:

- `custom_claim`
- `polymarket_market_id`
- `polymarket_url`

That validation happens in `ManualAnalysisCreateRequest`.

The frontend also lets the user provide:

- an optional template override
- an optional deadline string
- an `include_live_x_intelligence` toggle
- an `include_premium` toggle

## 2. The strategic idea behind manual analysis

The strategy is not "ask an LLM for an answer."

The strategy is:

1. Turn the user’s question into a structured proposition with explicit YES and NO conditions.
2. Gather a conservative source set around that proposition.
3. Ground those sources into ranked passages instead of trusting raw snippets.
4. Extract candidate facts and verify them against source context.
5. Classify each fact by its role in the proposition.
6. Convert only directional, eligible facts into weighted factors.
7. Build either:
   - a numeric range plus recommendation, or
   - a qualitative read plus an explanation for why numeric output was withheld.

In other words, the pipeline tries to separate:

- context
- directional evidence
- market edge

Those are not treated as the same thing.

## 3. What happens when a user submits a manual run

The manual form sends a payload through `createManualAnalysis(...)` in the frontend API client.

The backend route `POST /api/analyses/manual` then creates an `AnalysisRequest` with:

- `mode = manual`
- a resolved input type (`custom_claim`, `market_id`, or `market_url`)
- the chosen or auto-detected template
- the raw input payload
- a fresh progress payload

The request is queued and dispatched to `AnalysisProcessor.process_request(...)`.

## 4. Stage-by-stage strategy

The pipeline stages are:

1. Normalize Input
2. Market Lookup
3. Rule Parse
4. Retrieval
5. Social Intelligence
6. Fact Extraction
7. Fact Verification
8. Evidence Classification
9. Factor Mapping
10. Probability Estimation
11. Brief Generation
12. Complete

The app stores stage state in `progress_json`, which is what drives the live memo page while the run is still working.

## 5. Rule-parse strategy

The rule-parse stage is the first real strategic step.

Its job is to convert a user question into a scoring frame:

- `template_detected`
- `claim_family`
- `entity_names`
- `action`
- `yes_condition`
- `no_condition`
- `deadline_text`
- `official_domains`
- `clarity_score`
- `resolution_risk`
- `directional_scoring_policy`

### Template behavior

If the user does not force a template, the backend auto-detects one using keyword heuristics:

- legal phrases like `lawsuit`, `court`, `injunction`, `strike down` push toward `legal_case`
- macro phrases like `fed`, `rate cut`, `inflation` push toward `macro_policy`
- event phrases like `approve`, `filing`, `announce` push toward `official_event`
- sentiment phrases like `consensus`, `buzz`, `narrative` push toward `narrative_manual`
- otherwise it falls back to `generic_manual`

### Why this matters

The chosen template affects:

- retrieval strategy
- which evidence roles can score direction
- template multiplier in factor weights
- base uncertainty
- whether commentary can count directionally
- whether live X runs by default

## 6. Retrieval strategy

Retrieval is not one search. It is a lane-based collection step.

The pipeline may add:

- the manual claim itself as a contextual source
- linked market rules and description if a Polymarket URL or ID was provided
- live X intelligence
- Tavily web/news search results

### Important retrieval rules

#### Manual claim input

If the input is a free-form claim, the question itself is stored as a `MANUAL_INPUT` source.

That source is context only. It helps frame the proposition, but it is not directional evidence by itself.

#### Market-linked input

If the request points at a Polymarket market, the market rules and description are also stored as contextual input.

That gives the system:

- market prior
- executable prices
- resolution wording

#### Live X intelligence

Live X runs only for manual requests.

If the user does not explicitly choose a value, the default behavior is:

- `official_event`: off by default
- `macro_policy`, `legal_case`, `narrative_manual`, `generic_manual`: on by default

The social strategy is:

- collect broader narrative context
- keep only trusted posts for the persisted trusted timeline
- downgrade the result to weak narrative-only context if no trusted posts survive the trust filter

Only high-trust or official social posts are eligible to contribute directionally.

Broader consensus is context, not truth.

#### Tavily search

Search behavior depends on the template:

- `macro_policy`: news-oriented search with official-domain bias
- `official_event`: official-domain oriented search
- `legal_case`: mixed strategy

For `legal_case`, the code now does two things:

1. a broad legal/news query to find relevant case coverage
2. a narrower official-domain query for docket/order material

That change matters because an official-only legal search can easily return irrelevant government PDFs that merely mention the same company or keyword.

### Grounding strategy

After retrieval, each source is grounded into:

- a cleaned document
- a small set of ranked passages

Relevance scoring rewards:

- overlap with the question
- overlap with YES terms
- overlap with NO terms
- explicit action matches
- entity matches
- official-source bonus

The system tries to score passages before it extracts facts, so later steps work from focused text instead of full noisy documents.

## 7. Fact strategy

The fact pipeline has three steps:

1. extract
2. verify
3. classify

### Fact extraction

The system extracts up to a handful of candidate facts per source.

Fallback extraction prefers:

- ranked grounded passages
- then source excerpts

It filters low-signal boilerplate and ignores sentences that do not intersect the question terms.

### Fact verification

Each extracted fact is verified against the best matching passage or excerpt context.

The verifier status becomes one of:

- `supported`
- `ambiguous`
- `rejected`

Verification directly affects factor weight later.

### Evidence-role classification

Each verified fact is classified into roles like:

- `outcome`
- `direct_support`
- `direct_contradiction`
- `commentary`
- `procedural`
- `timing`
- `background`
- `sentiment`

Then the backend normalizes that role again with template-specific logic.

This second pass is important because it stops superficially related facts from scoring direction when they are really just context.

### Legal-case normalization

Legal cases have extra safeguards.

For example:

- underlying order text can be downgraded to background
- procedural developments stay non-directional
- injunction wins/losses can count as directional legal evidence

That last rule is important for cases where interim court relief is the best available signal before a final merits decision.

## 8. Factor strategy

Facts do not go straight into scoring.

They first become `Factor` records.

Each factor gets:

- a stance: `yes`, `no`, or `neutral`
- a strength
- an evidence role
- `used_in_scoring = true/false`
- an exclusion reason if it is not directional
- a final numeric weight

### What is allowed to score direction

The pipeline refuses to score:

- background
- timing
- sentiment
- procedural developments

Commentary may or may not score depending on the claim family and source tier.

For example:

- `official_event`: commentary is not directional
- `macro_policy`: expert commentary can score
- `legal_case`: expert commentary can score

### Weight formula

Directional factors get a final weight from:

`source_weight * strength_multiplier * directness_multiplier * verification_multiplier * freshness_multiplier * uniqueness_multiplier * template_multiplier`

Key source weights today are:

- official primary: `0.45`
- official statement: `0.30`
- premium news: `0.25`
- expert analysis: `0.24`
- reputable news: `0.20`
- official social: `0.12`
- high-trust social: `0.10`

Important strategic consequences:

- official and expert material matters more than generic reporting
- ambiguous facts get discounted
- duplicate evidence gets damped by the uniqueness multiplier
- template choice changes how aggressively evidence is allowed to move the model

## 9. Probability strategy

The probability stage always emits a point estimate for completed runs.

It first computes:

- prior
- evidence score
- priced-in risk
- uncertainty
- confidence
- qualitative label

### Prior

If a market is linked, the prior comes from market prices.

If no market is linked, the logistic update starts from a neutral base through the scoring helpers.

### Evidence

The model sums directional factor weights into evidence.

Social evidence is capped, so social cannot dominate the run by itself.

### Uncertainty

Uncertainty starts with a template baseline and then widens or tightens based on:

- clarity score
- resolution risk
- priced-in risk
- absence of official sources
- lack of executable market prices
- wide market spread
- contradictory evidence
- social consensus strength

### Qualitative label

The qualitative label is still determined alongside the point estimate:

- `insufficient_basis`
- `mixed`
- `leans_yes`
- `leans_no`

### Point estimate vs uncertainty band

The main product now leads with the point estimate:

- `YES 58% / NO 42%`

The uncertainty band is still calculated:

- for confidence labeling
- for audit/explainer views
- for market-edge comparison when a market is linked

This means manual runs no longer hide the model probability just because the evidence base is thin. Thin evidence now lowers confidence and typically leaves the estimate closer to neutral instead.

## 10. Recommendation strategy

Recommendation is separate from inference.

The code can believe something leans YES and still refuse to recommend a trade.

### If there is no usable market edge

The recommendation becomes `analysis_only` when:

- no market is linked
- no executable prices are available
- numeric output is withheld

### If there is a linked market

The system compares the probability range against market asks with a friction buffer.

Possible labels are:

- `lean_yes`
- `lean_no`
- `no_edge`
- `needs_more_research`
- `analysis_only`

So the strategy is:

- first form a research view
- then separately decide whether the market setup justifies action

## 11. Memo strategy

The presentation layer turns the analysis into a memo-style output:

- headline
- thesis
- status note
- `what_it_means`
- `why_yes`
- `why_no`
- contextual but non-scored evidence
- caveats
- artifact status list

If the pipeline cannot support a number, the memo still explains:

- the qualitative read
- the best scored YES evidence
- the best scored NO evidence
- why no numeric estimate is being shown

That is deliberate. The product prefers explicit uncertainty over fake precision.

## 12. A concrete scenario

### Scenario

A user submits:

`Will Anthropic win its lawsuit against the DoD?`

as a `custom_claim`, with no linked Polymarket URL or market ID.

### What the code will do

1. Create a manual request with the claim as the primary input.
2. Auto-detect `legal_case`.
3. Build specific legal conditions rather than a generic binary frame:
   - YES if Anthropic wins meaningful court relief against the Department of Defense
   - NO if Anthropic loses, gets dismissed, or is denied relief
4. Store the raw question as a contextual manual-input source.
5. Run legal-case retrieval:
   - broad legal/news search for relevant coverage
   - narrower official-domain search for docket/order material
6. Ground the selected sources into ranked passages.
7. Extract and verify claims from those passages.
8. Classify claims like:
   - `judge granted a preliminary injunction` as directional YES-side legal evidence
   - pure procedure as contextual only
   - unrelated background about the dispute as background only
9. Convert eligible claims into weighted factors.
10. Compute a qualitative read and try the numeric gate.

### What the output will likely look like

Because the request has no linked market:

- the recommendation will still be `analysis_only`
- the run may still produce a qualitative label like `leans_yes`
- a numeric range may still be withheld if the evidence mix is too thin or too contextual

So the most likely behavior is:

- a research memo with real `Why yes` evidence
- low or medium confidence depending on source mix
- `analysis_only` as the recommendation because there is no executable market edge to evaluate

If the same case is submitted with a Polymarket URL or market ID, the strategy changes at the final stage:

- market prior can be used
- executable prices can be used
- the system can move from `analysis_only` into `lean_yes`, `lean_no`, `no_edge`, or `needs_more_research`

## 13. Current limitations worth knowing

These are important if you want to improve the strategy later.

### `include_premium` is limited but no longer dead

The form’s `include_premium` flag now controls whether paywalled premium-news search results are allowed into the retrieved source set.

That said, it still does not guarantee authenticated premium scraping. It affects source admission, not full subscription-grade document access.

### The manual claim itself does not count as evidence

It becomes a contextual source, not a directional factor.

### Social is deliberately capped

Social can modify the read, but it is not allowed to overpower grounded non-social evidence.

### Qualitative-only output is a feature, not always a bug

If the code cannot defend a numeric estimate, it is designed to say so explicitly rather than fabricate precision.

## 14. Short summary

The manual-analysis strategy is:

- parse the question into an explicit proposition
- retrieve conservatively
- ground passages before fact extraction
- verify before scoring
- score only eligible directional evidence
- separate research view from market action
- show qualitative output when numeric confidence is not justified

That makes manual analysis closer to a structured research desk than a raw chatbot answer.
