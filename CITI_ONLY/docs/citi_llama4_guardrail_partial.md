# CITI Hub — Llama 4 / GuardRail (`guardrail_last.GuardRail`)

GuardRail on CITI JupyterHub lives in module **`guardrail_last`** as class **`GuardRail`**.
This CITI_ONLY package wires that class only — **no OpenAI client in app code**.

## Hub call shape (notebook Cell 6)

```python
import os
from functools import partial
from guardrail_last import GuardRail

MODEL = "Llama-4-Scout-17B-16E-Instruct"
soeId = os.environ.get("SOEID") or os.environ.get("POLICY_SOEID") or ""  # set in env, never hardcode
GENERATION_TEMPERATURE = 0

GuardRail.INITIALIZE(soeId)
parse = partial(GuardRail.CHAT_COMPLETIONS_PARSE, model=MODEL, user=soeId)
generate = partial(GuardRail.CHAT_COMPLETIONS_CREATE, model=MODEL, user=soeId)

def build_messages(prompt, system_prompt=None):
    messages = [{"role": "user", "content": prompt}]
    if system_prompt is not None:
        messages.insert(0, {"role": "system", "content": system_prompt})
    return messages

# CREATE / PARSE return (r2d2_request_id, completion)
_req_id, c = generate(
    messages=build_messages("hello", "You are helpful."),
    temperature=GENERATION_TEMPERATURE,
    top_p=0.9,
)
text = c.choices[0].message.content
```

Pipeline code uses `create_guardrail_client(backend=GuardRail)`, which:

1. Calls `GuardRail.INITIALIZE(soeId)`
2. Invokes `CHAT_COMPLETIONS_CREATE` / `CHAT_COMPLETIONS_PARSE`
3. Unwraps `(request_id, completion)` before reading `choices[0].message.content`

## Env

```text
POLICY_LLM_PROVIDER=llama4
POLICY_LLM_MODEL=Llama-4-Scout-17B-16E-Instruct
SOEID=<your soeid>
```

Do **not** set app-level OpenAI keys; Hub GuardRail owns auth/certs.

## Expected status

```text
GUARDRAIL_CONNECTED GuardRailClient provider= llama4 model= Llama-4-Scout-17B-16E-Instruct
```

If status is `MOCK`, fix the import / SOEID / model id — do not claim live Llama.
