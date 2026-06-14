// POST { agent_id, token, picks:[{ticker,direction}] } — external agent submits exactly 3 of today's 6, once/day.
// Auth by agents.claim_token. House (game_roster) agents cannot self-submit. Mirrors game-submit-picks validation.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};
const todayUtc = () => new Date().toISOString().slice(0, 10);

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, "Content-Type": "application/json" } });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const { agent_id, token, picks } = await req.json();
    if (!agent_id || !token || !Array.isArray(picks)) return json({ success: false, error: "Missing agent_id, token, or picks" }, 400);
    if (picks.length !== 3) return json({ success: false, error: "Pick exactly 3 stocks" }, 400);
    for (const p of picks) {
      if (!p || typeof p.ticker !== "string" || !["long", "short"].includes(p.direction)) {
        return json({ success: false, error: "Invalid pick format" }, 400);
      }
    }
    const tickers = picks.map((p: { ticker: string }) => p.ticker);
    if (new Set(tickers).size !== 3) return json({ success: false, error: "Duplicate tickers" }, 400);

    const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const today = todayUtc();

    const { data: agent } = await supabase.from("agents")
      .select("id, claim_token, game_roster").eq("id", agent_id).maybeSingle();
    if (!agent || agent.claim_token !== token) return json({ success: false, error: "Invalid agent_id or token" }, 401);
    if (agent.game_roster) return json({ success: false, error: "House agents cannot self-submit" }, 409);

    const { data: pool } = await supabase.from("game_ticker_pool").select("ticker").eq("trade_date", today);
    const poolTickers = new Set((pool ?? []).map((r) => r.ticker));
    if (poolTickers.size === 0) return json({ success: false, error: "Today's stocks aren't ready yet" }, 409);
    for (const t of tickers) {
      if (!poolTickers.has(t)) return json({ success: false, error: `Ticker not in today's pool: ${t}` }, 400);
    }

    const { count: existing } = await supabase.from("game_agent_pick")
      .select("id", { count: "exact", head: true }).eq("agent_id", agent_id).eq("trade_date", today);
    if ((existing ?? 0) > 0) return json({ success: false, error: "Already submitted today" }, 409);

    const rows = picks.map((p: { ticker: string; direction: string }) => ({ agent_id, trade_date: today, ticker: p.ticker, direction: p.direction }));
    const { error: pickErr } = await supabase.from("game_agent_pick").insert(rows);
    if (pickErr) throw pickErr;
    await supabase.from("agents").update({ game_external: true }).eq("id", agent_id);

    return json({ success: true, trade_date: today, picks: rows.map((r) => ({ ticker: r.ticker, direction: r.direction })) }, 200);
  } catch (err) {
    console.error("game-submit-agent-picks error:", err);
    return json({ success: false, error: "Internal server error" }, 500);
  }
});
