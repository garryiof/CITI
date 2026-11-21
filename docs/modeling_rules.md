# Modeling rules

- No hallucinated requirements; unsupported inferences labeled for review.
- Nonprocedural policies emit `no_supported_process.json` — do not fabricate BPMN tasks.
- Scanned/image-only PDFs emit OCR-required warning; never invent text.
- Inferred edges use `derivation=inferred_for_review` when enabled.
