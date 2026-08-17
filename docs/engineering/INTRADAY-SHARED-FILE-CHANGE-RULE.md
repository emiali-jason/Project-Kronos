# Intraday Shared-File Change Rule

**Status:** Active Engineering Instruction
**Owner:** KRONOS Intraday Engineering Architect
**Scope:** KRONOS Intraday V1 engineering work

## Rule

An Intraday work order may not modify a Swing-owned or actively shared file
unless all three conditions hold:

1. The work order explicitly identifies the shared-file change.
2. An Intraday adapter cannot reasonably solve the need.
3. The change is bounded and protected by regression tests.

If an unexpected shared-file change is required, Engineering must stop and
return:

```text
SHARED-FILE CHANGE REQUIRED

File:
<path>

Reason:
<reason>

Can adapter solve it:
YES / NO

Recommended action:
<exact>
```

Engineering must not silently modify that file.

## Product naming

New product implementation uses explicit Intraday naming or lives inside the
`kronos.intraday` namespace. Ambiguous generic names outside a clearly
product-owned namespace are not used for Intraday product behavior.

## Post-recovery ownership map

- `kronos.browser.server` and `kronos.browser.views` preserve the committed
  Swing Browser implementation and expose bounded shared composition seams.
- Ordinary Intraday route and rendering changes belong in
  `kronos.browser.intraday_routes` and `kronos.browser.intraday_views`.
- Intraday runtime composition belongs in `kronos.application.intraday_runtime`.
- Intraday consumes DOMAIN-001 through `kronos.intraday.instrument` and
  DOMAIN-008 through `kronos.intraday.market_context`.
- Platform factual corrections remain with their owning platform domains.

The shared Browser files may not be changed for ordinary Intraday evolution.
