# SECURITY.md

- Report vulnerabilities privately through GitHub Security Advisories
  ("Report a vulnerability" on the repository's Security tab).
  **Never open a public issue for a vulnerability.**
- Acknowledgment within 72 hours; fix-or-plan within 14 days;
  coordinated disclosure after a fix ships.
- Supported: latest minor release, unless stated otherwise.
- Secrets never enter the repo — not code, config, fixtures, or history.
  CI uses Actions secrets; local dev uses untracked `.env` with a
  committed `.env.example` when one is needed.
- `install.sh` trusts exactly 1 third-party package source, the KiCad
  PPA, and verifies its signing key against the fingerprint pinned in
  the script. The FreeRouting JAR is verified against the pinned
  SHA-256. A fingerprint or checksum change is a reviewed commit, never
  an environment override in CI.
- For the agent: security-shaped work overrides normal routing. A
  security fix may ship out-of-band as a patch release at any time,
  without waiting for the weekly cycle.
