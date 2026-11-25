# ADR-0004 — Causal research samples, snapshots and prospective confirmation

**Status:** Proposed for research review, 2026-11-18. Production gates remain unaccepted.

Historical evaluation periods have been inspected repeatedly, and broker-native
timestamps cannot be presumed to be verified UTC. Reproducible experiments need
explicit separation of feature availability, later labels and execution evidence.

The research implementation therefore:

- Preserves original broker files and records source/code/package fingerprints.
- Stores features separately from forward labels, identifies source rows, and
  purges outcomes touching the next split boundary.
- Uses native-clock feature profiles explicitly; unverified seasonal conversion
  produces inferred timestamps and retains every unmapped original row.
- Captures current quote observation time on the host in UTC, keeping the broker
  event timestamp separately, and builds content-addressed snapshot schema v1.
- Filters future bars/releases before model-visible serialization. Missing or
  stale context blocks completeness; downstream readers recheck expiry and
  content identity rather than trusting an old completeness flag.
- Keeps snapshot research features distinct from the eleven-field historical
  classifier schema until a separately verified adapter is implemented.
- Records all available research reruns as a retrospective partial inventory.
  It does not present that inventory as a prospective exhaustive trial ledger.
- Registers an additional future confirmation window before it starts, retains
  frozen code/model copies, and rejects overlapping interim replay. Local hash
  anchors and application guards do not constitute independent timestamps or
  operating-system access control.

Weights, proprietary raw inputs and runtime artifacts stay outside Git. This
change introduces neither model promotion nor a broker order path. Deterministic
risk authorization and separate execution review remain independent requirements.

Consequences: experiments and current input packets can be replayed and audited,
but successful reproduction proves implementation consistency, not predictive
edge, complete UTC coverage or safe deployment. Calendar completeness, historical
clock reconciliation, executable costs, unseen results and independent review
remain outstanding. See documents 34–39 for evidence and negative tests.

Rollback: revert the research change on its feature branch or select the previous
code/model manifest. Do not overwrite archived inputs, registered protocols or
frozen artifacts; retain their identities as historical evidence.
