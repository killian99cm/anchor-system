# Anchor Optimization Design

Date: 2026-08-07
Status: Draft for review

## 1. Goal

Improve Anchor in five ways without changing the core investment philosophy:

1. Close rule loopholes that can cause inconsistent actions or accidental overtrading.
2. Increase risk-adjusted return rather than raw return.
3. Improve drawdown defense and regime-aware risk handling.
4. Make the system easier to maintain by consolidating shared logic and outputs.
5. Make daily use more intelligent and easier to operate.

This design intentionally does **not** add the promo-image work yet. The promo image will be handled after the optimization work is complete.

## 2. Non-Goals

- Do not change the meaning of the core Anchor rules.
- Do not introduce a new runtime framework or frontend stack.
- Do not redesign the dashboard visually in this pass.
- Do not expose live holdings or private desktop-only artifacts in public assets.
- Do not replace the existing single-JSON data flow with a new storage layer.

## 3. Current Problems

### 3.1 Rule loopholes

Anchor already has strong rules, but some actions are still driven by isolated signals. For example:

- DDX confirms entries, but it does not yet combine cleanly with price position.
- Stop-loss exists, but it does not explicitly account for regime context.
- Take-profit is disciplined, but it may cut strong trends too early.
- Cash reserve is fixed rather than regime-aware.

### 3.2 Return quality gaps

Anchor does not yet rank opportunities explicitly. This can lead to two unwanted behaviors:

- entering too early on weak signals,
- missing stronger trends because the system does not distinguish observation, probe, add, and expand states.

### 3.3 Risk control gaps

- Single-position risk logic and portfolio context are not fully linked.
- Time-stop and price-stop can conflict without a clear priority ladder.
- There is no unified operation freeze switch when the market or data is ambiguous.

### 3.4 Maintainability gaps

- Shared concepts such as drawdown baseline, monthly operation count, and risk status appear in multiple files.
- Some generated artifacts can drift from the JSON source of truth.
- Deployment and public artifacts are not fully separated from private operational data.

### 3.5 Ease-of-use gaps

- Daily operation still requires too much manual interpretation.
- Output hierarchy can be clearer for fast scanning.
- Error messages and status messages can be more actionable.

## 4. Recommended Design

### 4.1 Principle: one source of truth

`portfolio_data.json` remains the only authoritative data source. Every other artifact must be derived from it or validated against it.

Shared calculations should be consolidated into one reusable contract for:

- peak assets / drawdown baseline,
- monthly operation count,
- layer classification,
- rule status,
- risk state.

### 4.2 Principle: hard gates first, soft intelligence second

Any new intelligence must sit behind hard risk gates. The system should never “be smart” in a way that weakens discipline.

Priority order:

1. Safety and consistency.
2. Risk-adjusted return.
3. Maintainability.
4. Convenience and automation.

### 4.3 Principle: stateful but deterministic

Anchor should behave like a state machine, not a prediction engine.

For each trade decision, the system should determine:

- market regime,
- opportunity score,
- position state,
- risk state,
- allowed action.

The result must be deterministic from the same input data.

## 5. Functional Changes

### 5.1 Unified portfolio contract

Create one shared calculation contract used by `data_processor.py`, `rebuild.py`, `test_calculations.py`, and `smoke_test.py` for:

- drawdown baseline,
- monthly operation count,
- layer mapping,
- rule status,
- conclusion state.

The design should keep backward-compatible defaults but remove silent drift.

### 5.2 Cross-artifact consistency gate

Extend the validation flow so the following must agree before a rebuild is considered healthy:

- `portfolio_data.json`
- `portfolio_snapshot.json`
- `portfolio_analysis.html`
- `anchor-pro.html`

Checks should cover totals, dates, and baseline values. As a deployment hygiene fix, the public GitHub Pages workflow should follow the actual `main` branch instead of `master`.

### 5.3 Opportunity scoring

Add a non-binding opportunity score to improve return quality.

The score should classify opportunities into:

- Observe
- Probe
- Add
- Expand candidate

Inputs may include:

- DDX trend,
- price position,
- volume / turnover,
- existing holdings,
- market regime,
- monthly operation budget,
- negative-list restrictions.

This score should not directly replace the existing rules; it should help decide whether an action is worth considering.

### 5.4 Trend-strength awareness

Add a trend-strength regime so strong moves are not treated the same as weak rebounds.

Possible regimes:

- Weak
- Repair
- Strong trend
- Overheated

This regime can influence take-profit timing, cash target, and whether a probe can be upgraded to an add.

### 5.5 Risk regime state machine

Introduce a simple risk-state ladder:

- Defense
- Watch
- Normal
- Attack

This state determines:

- cash target range,
- whether new entries are allowed,
- how strict the probe/add gate should be,
- whether the system should freeze new actions.

### 5.6 Stop-loss confirmation window

Keep the -8% stop-loss rule, but when a position crosses the line, the system should first check whether the move is part of a broader regime failure or just a noisy dip.

The confirmation window should check:

- DDX direction,
- peer sector weakness,
- market regime,
- time-stop status,
- whether the position is already classified as weak.

If the confirmation conditions are not met, the system can wait one day and re-evaluate.

### 5.7 Strong-trend take-profit protection

Keep the current tiered take-profit logic, but allow a strong-trend exception when the trend is clearly healthy.

A position should be allowed to continue running when:

- DDX stays positive for at least 3 days,
- the sector outperforms the benchmark,
- turnover expands,
- the position does not show fast deterioration.

In that case, a planned take-profit can become a protected hold with an updated stop line.

### 5.8 Regime-aware cash target

Convert the cash reserve from a fixed target into a regime-aware target band:

- Defense: 15%–20%
- Normal: 12%–15%
- Attack: 8%–12%

The system chooses the band from market and portfolio conditions, but still keeps the existing cash-reserve role intact.

### 5.9 Operation freeze switch

Add a single freeze state that blocks new entries when:

- data is stale or missing,
- signals conflict,
- market conditions are extreme,
- monthly operation cap is reached,
- the system is in defense mode and a risk trigger is active.

Freeze should prevent new actions, not force liquidation.

### 5.10 Better daily usability

Standardize the output order in summaries and dashboard text:

1. Current state
2. Risk alerts
3. Allowed actions
4. Disallowed actions
5. Next watch points

Also make the short command workflow more consistent so common tasks can be triggered with fewer words.

## 6. Public/Private Boundary

Public-facing assets must use sanitized or example data only.

This means:

- no raw private holdings in social assets,
- no Desktop-only operational artifacts in public copy,
- no live portfolio numbers in public story packs,
- GitHub Pages should publish only public/demo assets.

## 7. Validation Plan

The design should be considered complete only when the following pass:

- calculation tests still pass,
- smoke tests still pass,
- rebuild output agrees with source JSON,
- HTML outputs agree on totals and dates,
- the public demo remains free of private data.

## 8. Scope Guardrails

This design intentionally leaves out:

- promo image generation,
- broad dashboard redesign,
- new trading strategies,
- new external dependencies,
- any change to core rule semantics.

If future work wants to go beyond these guardrails, it should be split into a separate spec.
