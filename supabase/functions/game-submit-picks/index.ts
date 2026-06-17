// supabase/functions/game-submit-picks/index.ts
// POST { device_id, picks:[{ticker,direction}] } — exactly 3 tickers from today's pool, once per day.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { XP } from "../_shared/game_logic.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};
const todayUtc = () => new Date().toISOString().slice(0, 10);

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const { device_id, picks } = await req.json();
    if (!device_id || !Array.isArray(picks)) {
      return new Response(JSON.stringify({ success: false, error: "Missing device_id or picks" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }
    if (picks.length !== 3) {
      return new Response(JSON.stringify({ success: false, error: "Pick exactly 3 stocks" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }
    for (const p of picks) {
      if (!p || typeof p.ticker !== "string" || !["long", "short"].includes(p.direction)) {
        return new Response(JSON.stringify({ success: false, error: "Invalid pick format" }),
          { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
      }
    }
    const tickers = picks.map((p) => p.ticker);
    if (new Set(tickers).size !== 3) {
      return new Response(JSON.stringify({ success: false, error: "Duplicate tickers" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const today = todayUtc();

    const { data: pool } = await supabase.from("game_ticker_pool")
      .select("ticker").eq("trade_date", today);
    const poolTickers = new Set((pool ?? []).map((r) => r.ticker));
    if (poolTickers.size === 0) {
      return new Response(JSON.stringify({ success: false, error: "Today's stocks aren't ready yet" }),
        { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }
    // 픽 잠금: 개장(13:30 UTC, EDT) 이후엔 제출 불가 — 가격 보고 고르는 것 방지
    const nowUtc = new Date();
    const openUtc = new Date(`${today}T13:30:00Z`);
    if (nowUtc >= openUtc) {
      return new Response(JSON.stringify({ success: false, error: "Picks are locked — the market is open. Come back before the next open." }),
        { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }
    for (const t of tickers) {
      if (!poolTickers.has(t)) {
        return new Response(JSON.stringify({ success: false, error: `Ticker not in today's pool: ${t}` }),
          { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
      }
    }

    const { data: player } = await supabase.from("players").select("id").eq("device_id", device_id).maybeSingle();
    if (!player) {
      return new Response(JSON.stringify({ success: false, error: "Unknown player. Call game-state first." }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    const { count: existing } = await supabase.from("game_pick")
      .select("id", { count: "exact", head: true }).eq("player_id", player.id).eq("trade_date", today);
    if ((existing ?? 0) > 0) {
      return new Response(JSON.stringify({ success: false, error: "You already submitted today" }),
        { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    const rows = picks.map((p) => ({ player_id: player.id, trade_date: today, ticker: p.ticker, direction: p.direction }));
    const { error: pickErr } = await supabase.from("game_pick").insert(rows);
    if (pickErr) throw pickErr;

    const { error: ledgerErr } = await supabase.from("game_xp_ledger")
      .insert({ player_id: player.id, trade_date: today, reason: "submit_pick", xp_delta: XP.SUBMIT });
    if (!ledgerErr) {
      const { data: cur } = await supabase.from("players").select("xp").eq("id", player.id).single();
      await supabase.from("players").update({ xp: (cur?.xp ?? 0) + XP.SUBMIT }).eq("id", player.id);
    }

    return new Response(JSON.stringify({ success: true, xp_awarded: XP.SUBMIT }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-submit-picks error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
