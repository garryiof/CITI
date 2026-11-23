import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

type JsonBody = Record<string, unknown>;

const readJsonBody = (req: {
  on: (event: string, cb: (chunk?: Buffer) => void) => void;
}): Promise<JsonBody> =>
  new Promise((resolveBody, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk?: Buffer) => {
      if (chunk) chunks.push(chunk);
    });
    req.on("end", () => {
      try {
        resolveBody(JSON.parse(Buffer.concat(chunks).toString("utf8")) as JsonBody);
      } catch (reason) {
        reject(reason);
      }
    });
    req.on("error", reject);
  });

const sendJson = (
  res: { statusCode: number; setHeader: (k: string, v: string) => void; end: (b: string) => void },
  status: number,
  payload: unknown,
) => {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(payload));
};

const safeWorkflowId = (value: unknown): string | null => {
  const id = typeof value === "string" ? value.trim() : "";
  return /^[A-Za-z0-9_-]+$/.test(id) ? id : null;
};

/**
 * Local write APIs for the viewer (dev server only):
 * - POST /api/review-status  { workflow_id, review_status }
 * - POST /api/save-workflow  { workflow_id, kind: "json"|"bpmn", content }
 */
function outputsWriteApi(): Plugin {
  const outputsDir = resolve(__dirname, "../outputs");

  return {
    name: "outputs-write-api",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (req.method !== "POST") {
          next();
          return;
        }

        try {
          if (req.url === "/api/review-status") {
            const body = await readJsonBody(req);
            const workflowId = safeWorkflowId(body.workflow_id);
            const status = body.review_status;

            if (!workflowId) {
              sendJson(res, 400, { error: "Invalid workflow_id." });
              return;
            }
            if (status !== "PENDING" && status !== "APPROVED") {
              sendJson(res, 400, {
                error: "review_status must be PENDING or APPROVED.",
              });
              return;
            }

            const filePath = resolve(outputsDir, `${workflowId}.json`);
            if (!filePath.startsWith(outputsDir) || !existsSync(filePath)) {
              sendJson(res, 404, { error: "Workflow JSON not found." });
              return;
            }

            const workflow = JSON.parse(readFileSync(filePath, "utf8")) as JsonBody;
            workflow.review_status = status;
            writeFileSync(filePath, `${JSON.stringify(workflow, null, 2)}\n`, "utf8");
            sendJson(res, 200, {
              ok: true,
              workflow_id: workflowId,
              review_status: status,
            });
            return;
          }

          if (req.url === "/api/save-workflow") {
            const body = await readJsonBody(req);
            const workflowId = safeWorkflowId(body.workflow_id);
            const kind = body.kind;
            const content = body.content;

            if (!workflowId) {
              sendJson(res, 400, { error: "Invalid workflow_id." });
              return;
            }
            if (kind !== "json" && kind !== "bpmn") {
              sendJson(res, 400, { error: 'kind must be "json" or "bpmn".' });
              return;
            }
            if (typeof content !== "string" || !content.trim()) {
              sendJson(res, 400, { error: "content must be a non-empty string." });
              return;
            }

            const ext = kind === "json" ? "json" : "bpmn";
            const filePath = resolve(outputsDir, `${workflowId}.${ext}`);
            if (!filePath.startsWith(outputsDir)) {
              sendJson(res, 400, { error: "Invalid path." });
              return;
            }

            if (kind === "json") {
              // Validate JSON before writing so we never corrupt the file.
              JSON.parse(content);
              writeFileSync(filePath, content.endsWith("\n") ? content : `${content}\n`, "utf8");
            } else {
              writeFileSync(filePath, content, "utf8");
            }

            sendJson(res, 200, {
              ok: true,
              workflow_id: workflowId,
              kind,
              path: `outputs/${workflowId}.${ext}`,
            });
            return;
          }
        } catch (reason: unknown) {
          sendJson(res, 500, {
            error: reason instanceof Error ? reason.message : "Write failed.",
          });
          return;
        }

        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), outputsWriteApi()],
  publicDir: resolve(__dirname, "../outputs"),
  server: {
    fs: {
      allow: [resolve(__dirname, "..")],
    },
  },
});
