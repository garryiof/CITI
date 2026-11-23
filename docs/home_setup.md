# Home setup — policy folder + OpenAI key

For a blank home machine. Skip section 0 / this guide on CITI JupyterHub.

## 1. Install packages

In `notebooks/00_RUN_ONE_POLICY.ipynb`, run **section 0** once, then **restart the kernel**.

## 2. Put your policy file in `policies/`

1. Copy your document into the repo `policies/` folder (see `policies/README.md`).
2. Supported: `.html`, `.docx`, `.pdf` (text PDF).
3. In the notebook **Config** cell, change:

```python
POLICY_ID = "MY_POLICY_001"   # folder name under policy_runs/
POLICY_PATH = ROOT / "policies" / "my_policy.docx"
```

Default fixture (no personal file yet):

```python
POLICY_PATH = ROOT / "tests" / "fixtures" / "synthetic_policy.html"
```

## 3. Add your OpenAI API key

**Never commit the key.** Prefer one of these:

### Option A — `.env` file (recommended)

```powershell
cd D:\PORTFOLIO\CITI
Copy-Item .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
```

The notebook Config cell loads `.env` automatically (does not overwrite vars already set in the shell).

### Option B — PowerShell for this session

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:POLICY_LLM_PROVIDER = "openai"
```

### Option C — Notebook cell only (temporary)

In the LLM provider cell you can set:

```python
os.environ["OPENAI_API_KEY"] = "sk-..."   # clear before sharing the notebook
```

Do not leave a real key in a saved `.ipynb`.

## 4. Choose provider

**CITI Hub (default):** Llama 4 via GuardRail — do **not** set an OpenAI key.

```text
POLICY_LLM_PROVIDER=llama4
POLICY_LLM_MODEL=<exact Hub model id>
SOEID=<your soeid>
```

**Home OpenAI (optional):**

```text
POLICY_LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
POLICY_LLM_MODEL=gpt-4o-mini
```

## 5. Run

Run All from Bootstrap onward (through section 3b once). Artifacts: `policy_runs/<POLICY_ID>/<RUN_ID>/`. Offline pack: `notebooks/offline_p2b/` (main + role tabs). Zip for handoff: double-click `pack_offline_demo.bat` → `notebooks/offline_p2b_OFFLINE_DEMO.zip`. Demo: open `offline_p2b/index.html` via `file://`.

If rebuilding the offline pack and `offline_p2b/vendor` is missing bpmn-js, run `npm install` once in `policies2BPMN/viewer` (then re-run section 3b or `pack_offline_demo.bat`). Cursor prompts/plans live under `docs/cursor_prompts/` (not the repo root).

## Checklist

| Step | Done when |
|---|---|
| Packages | section 0 succeeded + kernel restarted |
| Policy path | `POLICY_PATH.exists()` is `True` |
| Key | `OPENAI_CONNECTED` printed (not `OPENAI_NOT_CONNECTED`) |
| Provider | `provider= openai` |
