# Development workflow

1. Create an issue linked to a roadmap phase; define acceptance tests first.
2. Work on a branch; use PRs even for a single maintainer when practical.
3. Update architectural decision records for system-level changes.
4. Capture experiment provenance: dataset hash, time ranges, code commit, random seed, cost assumptions.
5. Changes in risk execution, label generation, temporal joins, permission boundaries, and source import require review and negative tests.
6. Never auto-update upstream packages or snapshots. Lock dependency resolutions for each reproducible training/deployment environment.
7. The live execution switch remains absent until reviewed separately.
