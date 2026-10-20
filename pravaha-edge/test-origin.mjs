// Mock Render backend for integration testing of the PRAVAHA edge Worker.
// Run: node test-origin.mjs  (listens on 127.0.0.1:8799)
import http from "node:http";

const PORT = 8799;
let hits = 0;

function readBody(req) {
  return new Promise((resolve) => {
    let d = "";
    req.on("data", (c) => (d += c));
    req.on("end", () => resolve(d));
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const token = req.headers["x-friend-token"] || req.headers["authorization"] || "";
  console.log(`ORIGIN ${req.method} ${url.pathname} token=${token ? "present" : "MISSING"}`);

  if (url.pathname === "/api/bars/TEST") {
    hits++;
    if (!token) {
      res.writeHead(401, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "authentication required" }));
      return;
    }
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ symbol: "TEST", bars: [1, 2, 3], n: hits }));
    return;
  }
  if (url.pathname === "/api/portfolio") {
    res.writeHead(403, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "private records" }));
    return;
  }
  if (url.pathname === "/api/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok" }));
    return;
  }
  if (url.pathname === "/api/boom") {
    res.writeHead(500, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "boom" }));
    return;
  }
  if (url.pathname === "/api/_hits") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ hits }));
    return;
  }
  if (url.pathname === "/api/screen" && req.method === "POST") {
    const body = await readBody(req);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: true, echo: body }));
    return;
  }
  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: "not found" }));
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`MOCK_ORIGIN_READY on ${PORT}`);
});
server.on("error", (e) => { console.error("ORIGIN_ERR", e); process.exit(1); });
process.on("SIGTERM", () => { server.close(); process.exit(0); });
process.on("SIGINT", () => { server.close(); process.exit(0); });
