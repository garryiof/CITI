# JupyterHub-only execution

The sole required UX is `notebooks/00_RUN_ONE_POLICY.ipynb`.

Forbidden on the product path: `python -m`, CLI, shell/PowerShell, `!` magics, `%pip`, subprocess installs, local HTTP server.

Business logic lives in importable `.py` modules under `src/policy_knowledge/`. Notebook cells orchestrate only.
