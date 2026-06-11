// supabase/functions/game-submit-picks/index.ts
// POST { device_id, picks:[{ticker,direction}] } — 오늘 풀의 종목 중 정확히 3개, 하루 1회.
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
      return new Response(JSON.stringify({ success: false, error: "정확히 3개를 선택해야 합니다" }),
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
      return new Response(JSON.stringify({ success: false, error: "종목이 중복되었습니다" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const today = todayUtc();

    const { data: pool } = await supabase.from("game_ticker_pool")
      .select("ticker").eq("trade_date", today);
    const poolTickers = new Set((pool ?? []).map((r) => r.ticker));
    if (poolTickers.size === 0) {
      return new Response(JSON.stringify({ success: false, error: "오늘의 종목이 아직 준비되지 않았습니다" }),
        { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }
    for (const t of tickers) {
      if (!poolTickers.has(t)) {
        return new Response(JSON.stringify({ success: false, error: `오늘 풀에 없는 종목: ${t}` }),
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
      return new Response(JSON.stringify({ success: false, error: "오늘은 이미 제출했습니다" }),
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
