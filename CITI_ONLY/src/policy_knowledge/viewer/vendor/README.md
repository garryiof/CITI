# Approved vendor JavaScript assets

Place **approved** offline builds here. Do not download from the public internet inside JupyterHub without authorization.

## Expected filenames

| Asset | Expected path under `vendor/` |
|---|---|
| bpmn-js Navigated Viewer (UMD + CSS as provided by approved package) | `bpmn-navigated-viewer.min.js` (and companion CSS if required) |
| Cytoscape.js UMD | `cytoscape.min.js` |
| License texts | `LICENSES/` or sibling `*.LICENSE` files |

Exact filenames are enforced by `validate_offline_demo` / vendor readiness checks. Until approved bytes are present:

- interactive Knowledge Map / BPMN tabs are **not** demo-ready
- structural unit tests may use clearly labeled non-production stubs
- readiness reports must fail interactive claims honestly

## Approval placeholder

- [x] bpmn-js Navigated Viewer bytes copied (bpmn-js 18.21.0, `dist/bpmn-navigated-viewer.production.min.js`)
- [x] cytoscape.min.js copied (cytoscape 3.34.0, `dist/cytoscape.min.js`)
- [x] license texts present (`LICENSES/`)
- [ ] SHA256 recorded (optional but recommended)

Copy these files into each run’s `demo/` directory at build time — never rely on CDN or absolute Hub paths.
