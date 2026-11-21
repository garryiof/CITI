# Archive and transfer policy

Archiving ≠ transferring. `TransferPolicy` defaults deny workstation DEMO ZIP transfer.
`include_policy_excerpts_in_demo` defaults **true** so local `demo/data.js` always feeds the HTML with parsed text.

- FULL ZIP excludes `archive/` (no recursive self-inclusion).
- DEMO ZIP = `demo/` only (subject to transfer gates).
- Content review inventory + checksums + `ARCHIVE_REPORT` before any transfer claim.
