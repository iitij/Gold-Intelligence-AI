# Security, reproducibility and operations

## Minimum controls

- Repository private by default until deliberate publication/licensing review.
- No secrets committed, even in demos. Use environment/secret manager on host; separate least-privilege demo credentials.
- Local LLM endpoints bind to 127.0.0.1; no uncontrolled remote tools, prompt injection protection, read-only agent privileges.
- Use dependency pinning + hashes in reproducible deployment builds; SBOM and vulnerability triage on frozen code. No automatic upstream synchronization.
- Sign/checksum model artifacts, verify read-only model registry and source provenance, prevent untrusted pickle loads.
- GitHub Actions has least permissions (`contents: read`), secrets absent from PR CI.

## Monitoring

Quotes freshness, spread, broker connection, order lifecycle, risk rejects, model drift, calibration drift, inference latency, P&L differences vs simulation, policy and model revision, clock synchronization, memory/GPU and file-system exhaustion.

## Incident response

1. Disable submission of all new orders immediately and preserve forensic logs.
2. Reconcile broker positions and pending orders before any restart.
3. Capture timestamps and revisions with secrets redacted.
4. Restore last approved model/config or fail closed to paper-only.
5. Document incident and test failure scenario before reenablement.

## Backups

Back up manifests, immutable market data (subject to licensing), model/checkpoint hashes, split definitions, experiment registry and audit logs. Verify restore exercises, retention and encryption. Never include authentication material in public issue attachments.

## Deployment architecture

Separate research and inference processes. One active trader enforced at execution gateway; no concurrent independent agents issuing orders. Reproducible container/venv and isolated MT5 bridge. Demo environment only before production gates pass.

### P10-02 local restore exercise

The Headway 11–13 November 2026 archive was extracted into a fresh directory.
All 2,061 raw batch fingerprints matched the diagnostic manifest. Using the
existing locked CPU environment, training CSV and replay interval metadata,
the restored batches produced a byte-identical model comparison report.
Local evidence is in `artifacts/headway-restore-check.rYhODT/report.json`.
Encryption, off-device recovery and restoring the other inputs are still
outstanding for the full P10-02 exercise.
