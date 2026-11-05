// ToolGuest ratings API.
//
// GET  /api/ratings?tool=<id>  -> { average, count, yourRating, ratedAt, editableUntil }
// POST /api/ratings            -> { average, count, yourRating, changed, rereview }
//                                 body { tool, stars }
//
// A visitor can always change their score but never delete it: only 1-5 is
// accepted, and the voter hash keeps one entry per browser so a change adjusts
// the sum without being counted twice.
//
// A score can be changed freely inside the edit window (24h from the first
// rating). After that the same visitor's next tap counts as a fresh review:
// the sum and the count both move, and a new window opens. The window is
// measured from the first rating, not the last edit, so a visitor cannot keep
// it alive forever by editing.
//
// Data lives in Upstash Redis over its REST API, so there is no client
// library to install and no connection pool to manage. Each tool keeps two
// keys:
//
//   tg:r:<tool>  hash { sum, count }             the public aggregate
//   tg:v:<tool>  hash { <voter hash>: "stars|ms" }  one entry per browser
//
// The voter hash is derived from the client IP, so no raw IP is ever stored.

const MAX_STARS = 5;
const EDIT_WINDOW_MS = 24 * 60 * 60 * 1000;

// A voter entry is "stars|timestamp". Older entries were written as a bare
// number, so both shapes are read and a bare number is treated as just-rated.
function parseVoter(raw) {
  if (raw === null || raw === undefined || raw === "") return null;
  const parts = String(raw).split("|");
  const stars = Number(parts[0]);
  if (!Number.isFinite(stars) || stars < 1 || stars > MAX_STARS) return null;
  const at = parts.length > 1 ? Number(parts[1]) : Date.now();
  return { stars, at: Number.isFinite(at) ? at : Date.now() };
}

function config() {
  const url = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) throw new Error("Redis REST credentials are not configured");
  return { url, token };
}

// Batched commands go to the /pipeline endpoint, which answers with one
// { result } entry per command. A plain POST to the base URL accepts only a
// single flat command, so it cannot carry the multi-step writes below.
async function redis(commands) {
  const { url, token } = config();
  const res = await fetch(`${url.replace(/\/+$/, "")}/pipeline`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(commands),
  });
  const body = await res.json().catch(() => null);
  if (!res.ok || !Array.isArray(body)) {
    throw new Error(`Upstash responded ${res.status}: ${JSON.stringify(body).slice(0, 160)}`);
  }
  return body.map((entry) => (entry && entry.error ? null : entry && entry.result));
}

function safeTool(value) {
  const tool = String(value || "home")
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "");
  return tool.slice(0, 64) || "home";
}

function voterHash(req) {
  const forwarded = req.headers["x-forwarded-for"];
  const ip = (forwarded ? forwarded.split(",")[0] : req.socket?.remoteAddress || "unknown").trim();
  const secret = process.env.KV_REST_API_TOKEN || "toolguest";
  // Only needs to be stable per visitor, and it keeps raw IPs out of the
  // database, so a small non-cryptographic digest is enough.
  let h = 2166136261;
  const input = secret + "|" + ip;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(36);
}

// HGETALL answers with a flat [field, value, field, value, ...] array, so the
// two shapes are normalised into one.
function toStats(raw) {
  let sum = 0;
  let count = 0;
  if (Array.isArray(raw)) {
    for (let i = 0; i < raw.length; i += 2) {
      if (raw[i] === "sum") sum = Number(raw[i + 1]) || 0;
      if (raw[i] === "count") count = Number(raw[i + 1]) || 0;
    }
  } else if (raw && typeof raw === "object") {
    sum = Number(raw.sum) || 0;
    count = Number(raw.count) || 0;
  }
  return {
    count,
    average: count ? Math.round((sum / count) * 100) / 100 : 0,
  };
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("Content-Type", "application/json");

  try {
    const voter = voterHash(req);

    if (req.method === "GET") {
      const tool = safeTool(req.query?.tool || "home");
      const [raw, mine] = await redis([
        ["HGETALL", `tg:r:${tool}`],
        ["HGET", `tg:v:${tool}`, voter],
      ]);
      const stats = toStats(raw);
      const vote = parseVoter(mine);
      if (!vote) return res.status(200).json(stats);
      return res.status(200).json({
        ...stats,
        yourRating: vote.stars,
        ratedAt: vote.at,
        editableUntil: vote.at + EDIT_WINDOW_MS,
        canEdit: Date.now() < vote.at + EDIT_WINDOW_MS,
      });
    }

    if (req.method !== "POST") {
      res.setHeader("Allow", "GET, POST");
      return res.status(405).json({ error: "Method not allowed" });
    }

    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    const tool = safeTool(body.tool);
    const stars = Math.round(Number(body.stars));
    // Only a real score is accepted. A rating can be changed but never
    // deleted, so 0 and anything above five are rejected outright.
    if (!Number.isFinite(stars) || stars < 1 || stars > MAX_STARS) {
      return res.status(400).json({ error: `stars must be 1-${MAX_STARS}` });
    }

    const aggregate = `tg:r:${tool}`;
    const voters = `tg:v:${tool}`;

    const [previous] = await redis([["HGET", voters, voter]]);
    const prior = parseVoter(previous);
    const now = Date.now();
    const withinWindow = prior !== null && now - prior.at < EDIT_WINDOW_MS;

    let results;
    let rereview = false;

    if (prior === null) {
      // First rating from this browser: sum and count both move.
      results = await redis([
        ["HINCRBY", aggregate, "sum", stars],
        ["HINCRBY", aggregate, "count", 1],
        ["HSET", voters, voter, `${stars}|${now}`],
      ]);
    } else if (withinWindow) {
      // Same visitor changing their mind inside the window: adjust the sum,
      // keep the count, and keep the original timestamp so the window does not
      // slide forward on every edit.
      const delta = stars - prior.stars;
      results = await redis([
        delta ? ["HINCRBY", aggregate, "sum", delta] : ["HGET", aggregate, "sum"],
        ["HGET", aggregate, "count"],
        ["HSET", voters, voter, `${stars}|${prior.at}`],
      ]);
    } else {
      // The window has closed, so this is a fresh review: the old score stays in
      // the aggregate and the new one is added on top, so both sum and count
      // move, and a new window opens from now.
      rereview = true;
      results = await redis([
        ["HINCRBY", aggregate, "sum", stars],
        ["HINCRBY", aggregate, "count", 1],
        ["HSET", voters, voter, `${stars}|${now}`],
      ]);
    }

    const [sum, count] = results;

    return res.status(200).json({
      count: Number(count) || 0,
      average: count ? Math.round((Number(sum) / Number(count)) * 100) / 100 : 0,
      yourRating: stars,
      changed: prior !== null && withinWindow,
      rereview,
      ratedAt: rereview || prior === null ? now : prior.at,
      editableUntil: (rereview || prior === null ? now : prior.at) + EDIT_WINDOW_MS,
    });
  } catch (error) {
    return res.status(500).json({ error: String(error.message || error) });
  }
};
