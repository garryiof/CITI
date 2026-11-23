# Your policy documents (CITI Hub)

Put the policy file you want to analyze here, then point the notebook at it.

## Supported formats

- `.html` / `.htm`
- `.docx`
- `.pdf` (text-extractable; image-only PDFs need OCR, which is off by default)

## Steps

1. Copy your file into this folder, e.g. `policies/my_policy.docx`.
2. In the notebook **Config** cell, set:

```python
POLICY_ID = "MY_POLICY_001"
POLICY_PATH = ROOT / "policies" / "my_policy.docx"
```

3. Outputs land under `policy_runs/<POLICY_ID>/<RUN_ID>/` (gitignored).

## Safety

- Do **not** commit confidential real policies to git.
- Keep SOEID and other Hub secrets out of this folder — use Hub secrets / `.env`.
