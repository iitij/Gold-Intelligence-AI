# Create repository and publish all project artifacts

**The connected GitHub integration in this session cannot create a new repository.** It can write files/issues into an existing writable repository. No unrelated existing repository was modified. Use an empty new private GitHub repository (recommended name `gold-intelligence-ai`). Verify the target owner.

## Publishing without a GitHub create-repository API

This connector can create issues and write files only after the new repository exists; permissions do not add a `create repository` action to the available toolset. The CLI script below creates a private repository and pushes the safe bootstrap. Never use another existing repository as a workaround.

## Via GitHub CLI on workstation (recommended)

```bash
# prerequisite: install gh (GitHub CLI), then: gh auth login
# unpack the archive and enter the project directory
cd gold-intelligence-ai
bash scripts/bootstrap_publish.sh iitij/gold-intelligence-ai
# only after the repository exists:
python scripts/publish_issues.py --repo iitij/gold-intelligence-ai --dry-run
python scripts/publish_issues.py --repo iitij/gold-intelligence-ai --confirm
```

If GitHub repository was created already (empty), use `git remote add origin ...` and `git push -u origin main` rather than `gh repo create`. Do not include `vendor/snapshots` until their licenses and security have been reviewed; their initial import is a separate PR.

## GitHub settings recommended

Private visibility, no forced pushes to main, branch protection with CI, private vulnerability reporting, least-privilege collaborators, signed release tags if supported, restricted Actions secrets, labels imported by issue script. No deployment to live account. Project board optional; Issues are the authoritative task database.

## Source and model artifact handling

Source lock contains commit hashes; vendor script imports a one-time revision and refuses overwrite. Large model weights/data are not GitHub blobs; store checksums and manifest with local/object-storage paths and access rights. No credential in repo.
