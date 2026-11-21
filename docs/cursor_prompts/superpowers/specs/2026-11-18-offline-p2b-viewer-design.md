# Offline policies2BPMN viewer — short design (approved)

**Intent:** Same interface and functionality as `policies2BPMN` viewer, openable as offline HTML via `file://`, driven from `notebooks/00_RUN_ONE_POLICY.ipynb`. Do not modify `policies2BPMN/`.

**Approach picked:** A — notebook packages a self-contained offline folder from `policies2BPMN/outputs` (reference read only).

**Goals:** Workflow rail, BPMN canvas, element detail/traceability, legend, duplicates, analysis, overview phases, role switch; zoom/fit; drag + reset when Modeler UMD available; persistence via `localStorage` + Download.

**Non-goals:** Editing `policies2BPMN/`; replacing existing tabbed `demo/` POC; Vite/ESM/`fetch` under `file://`.

**Design:** Classic scripts + embedded `data.js` (`window.P2B_DATA`); UMD bpmn-js Modeler copied at pack time from reference `node_modules`; notebook cell invokes builder and prints open path.
