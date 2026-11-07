# Vendor policy

Read [`docs/adr/0001-frozen-upstream.md`](../docs/adr/0001-frozen-upstream.md), [`sources/sources.lock.json`](../sources/sources.lock.json) and [`docs/10-LICENSING.md`](../docs/10-LICENSING.md). Components are frozen to known SHAs, LICENSE files kept, and patches made only inside this repo. A curated file snapshot is **not** a functioning vendored application. Do not enable broker connections on the basis of snapshots; do not import AGPL or unlicensed code into core.
