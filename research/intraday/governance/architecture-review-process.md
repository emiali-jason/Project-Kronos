# Architecture Review Process

## Entry Criteria

An architecture candidate may enter review only when it references at least one extracted principle, all originating research notes, the relevant evidence profiles and convergence record, assumptions, limitations, and validation questions.

## Review Questions

1. What decision or responsibility problem is being addressed?
2. Is the candidate technology-neutral and parameter-free?
3. Does it preserve separation from KRONOS Swing production?
4. Does it depend on implementation content disguised as a principle?
5. Are source claims, extracted principles, and reviewer interpretation distinct?
6. Are evidence sources meaningfully independent?
7. What conflicting evidence or alternative responsibility boundaries exist?
8. Can the candidate be falsified or rejected?
9. Is validation feasible without outcome leakage or hindsight?
10. What would be the consequence of false acceptance or false rejection?

## Review Outcomes

- `ARCHITECTURE REVIEW`: review remains open.
- `VALIDATION REQUIRED`: candidate is sufficiently defined to enter the queue but is not approved.
- `REJECTED`: candidate fails relevance, evidence, scope, or responsibility review; preserve rationale.
- `ACCEPTED`: permitted only after completed validation and explicit approval.

## Independence

The person or process validating a candidate should not rely only on the originating source or its summary. Material conflicts must be recorded, not resolved by preference.

## Traceability

Every candidate must link backward to extracted principles and research notes and forward to validation records, rejected concepts, or accepted principles. Candidate files remain the master record; notes reference candidate IDs rather than duplicating candidate content.

## Decision Boundary

Architecture review never authorises code, Pine Script, TradingView logic, parameters, thresholds, or production changes.
