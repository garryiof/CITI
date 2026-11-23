# policies2BPMN — how to run

Standalone Policy → BPMN workflow viewer (Windows).

## Prerequisites

| Need | For |
|------|-----|
| **Node.js 18+** and npm | Viewer (required) |
| **Python 3.10+** | Only if you regenerate BPMN/JSON from the policy HTML |

Pre-built artifacts already live in `outputs/`, so for a normal demo you only need the viewer.

---

## Quick start (viewer)

1. Double-click **`start-viewer.bat`** in this folder  
   *(or from a terminal: `policies2BPMN\start-viewer.bat`)*
2. Wait until Vite prints a local URL (usually **http://localhost:5173**).
3. Open that URL in your browser.
4. Stop the server with **Ctrl+C** in the batch window.

First run runs `npm install` automatically if `viewer\node_modules` is missing.

### Manual equivalent

```bat
cd policies2BPMN\viewer
npm install
npm run dev
```

Then open **http://localhost:5173**.

---

## Optional: regenerate BPMN / JSON from the policy

Only needed after changing `scripts\one_off_convert.py` or the source policy HTML.

1. Double-click **`regenerate.bat`**  
   *(installs `beautifulsoup4` + `lxml` if needed, then runs the converter)*
2. Refresh or restart the viewer.

### Manual equivalent

```bat
cd policies2BPMN
pip install beautifulsoup4 lxml
python scripts\one_off_convert.py
```

Input: `policies\blackrockPTIP.html`  
Output: `outputs\*.json`, `outputs\*.bpmn`, `outputs\index.json`, `outputs\policy_source.html`

---

## What you can do in the viewer

- Browse workflows (including the merged **Entire Policy** diagram)
- Drag / rearrange diagram elements; **Save layout** writes to `outputs\` (dev server only)
- Click steps / events for details and jump to the original policy paragraph
- Switch role to **Policy Owner** to set review status Pending / Approved
- Use duplicate finder, workflow analysis, and legend tools

**Note:** Save layout and review-status writes work under `npm run dev` / `start-viewer.bat` only — not under a static build preview.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `node` not found | Install Node.js 18+ and reopen the terminal / bat |
| Port 5173 in use | Stop the other Vite process, or note the alternate port Vite prints |
| Diagrams look old after regenerate | Hard-refresh the browser (Ctrl+F5) or restart the viewer |
| `python` not found (regenerate) | Install Python 3.10+ and ensure “Add to PATH” was checked |
