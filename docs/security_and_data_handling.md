# Security and data handling

- No confidential real policies, SOEIDs, certs, or endpoints in tracked files.
- Develop with synthetic fixtures.
- Redact logs; never log prompt/completion text unless explicitly enabled and approved.
- Transfer gated by explicit `TransferPolicy` after content classification review.
