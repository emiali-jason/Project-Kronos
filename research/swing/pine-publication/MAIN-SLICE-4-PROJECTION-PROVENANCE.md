# KRONOS Swing V1 Main Slice 4 — Pine Projection Provenance

## Contract and authority

- Contract: `KRONOS-SWING-V1-PINE-EVIDENCE-V1`
- Contract version: `1.1`
- Publisher role: `CANDIDATE`
- Authority: `SHADOW_ONLY`
- Compatibility class: `IMPLEMENTATION_CHANGE_CONTRACT_COMPATIBLE`
- Transport: not implemented
- Production promotion: not authorized

## 4B — Commodity / MCX

- Frozen identity: `V2-SR2`
- Frozen source: `research/swing/pine-forensics/sources/V2-SR2/KRONOS_FUTURES_V2.pine`
- Frozen SHA-256: `d3048aa6d0f6f3a97585a4cc35d36d5839352d91ec8ff05d5989a495d341d54a`
- Frozen byte count: `356587`
- Candidate: `research/swing/pine-publication/candidates/4B-MCX/KRONOS_FUTURES_V2_PINE_EVIDENCE_V1_1_CANDIDATE.pine`
- Candidate SHA-256: `59f35175ea0c666fbadef00e6861f42e3c75b858a66891e3908657fd4bb0245d`
- Change boundary: exact frozen source bytes followed by an appended, namespaced
  evidence projection block.

## 4C — NSE

- Frozen identity: `NSE-V1-SR1`
- Frozen source: Sponsor-local `NSE-V1-SR1` publication-worktree artifact; its
  local absolute path is intentionally not published
- Frozen SHA-256: `33ddbdd416d905bf4cb925d45d08d9d4efccfe6db969b668d5101164c96b48f2`
- Frozen byte count: `350567`
- Candidate: `research/swing/pine-publication/candidates/4C-NSE/KRONOS_NSE_V1_SR1_PINE_EVIDENCE_V1_1_CANDIDATE.pine`
- Candidate SHA-256: `f7a5098b6c406303686a110849ba93c2a505ffa3e9bd2d6ba77b038aa1639a43`
- Change boundary: exact frozen source bytes followed by an appended, namespaced
  evidence projection block.

## Isolation qualification

The 4B product extension is guarded by the existing MCX product context and
publishes only MCX futures, reference-market, workstation and NOW/trigger
semantics. The 4C product extension is guarded by the existing NSE product
context and publishes only underlying, sector/parent, relative, opportunity,
readiness-reduction and NSE NOW-exclusion semantics. Static tests inspect these
contract-output assignments directly.

The frozen sources are a shared historical engine and already contain dormant
cross-product branches: V2-SR2 includes NSE branches and NSE-V1-SR1 includes
MCX/COMEX/NYMEX branches. Those bytes are retained unchanged because removing
them would violate the frozen-source and analytical-parity requirements. This
pre-existing whole-file condition is documented separately and is not
publication-contract contamination. It was introduced by neither 4B nor 4C.

## Verification boundary

Local tests prove frozen-prefix hash parity, the exact 14-domain contract
surface, explicit derivation classes, projection-only product isolation, and
absence of new analytical-engine or alert/webhook calls. TradingView Pine
compile and Add-to-chart validation require TradingView tooling and are not
claimed by these local checks.
