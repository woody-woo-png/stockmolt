// supabase/functions/game-leaderboard/index.ts
// GET ?type=return|xp&limit=20&device_id=...
//   return → lifetime capital (players + AI agents merged), pin-my-rank
//   xp     → CURRENT SEASON xp (derived from game_xp_ledger via RPC), pin-my-rank
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function todayUtc(): string { return new Date().toISOString().slice(0, 10); }

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const url = new URL(req.url);
    const type = url.searchParams.get("type") === "xp" ? "xp" : "return";
    const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "20", 10) || 20, 100);
    const deviceId = url.searchParams.get("device_id");
    const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const retPct = (cap: number) => Math.round(((cap - 100000) / 100000) * 10000) / 100;

    // ===== SEASON XP BOARD =====
    if (type === "xp") {
      const today = todayUtc();
      const { data: seas } = await supabase.from("game_seasons")
        .select("season_no, name, start_date, end_date")
        .lte("start_date", today).gte("end_date", today).maybeSingle();

      if (seas) {
        const { data: lb } = await supabase.rpc("get_season_leaderboard",
          { p_start: seas.start_date, p_end: seas.end_date, p_limit: limit });
        const rows = (lb ?? []).map((r: any, i: number) => ({
          rank: i + 1, is_ai: false, display_name: r.display_name, level: r.level,
          xp: Number(r.season_xp), capital: 0, return_pct: 0,
        }));
        let me = null;
        if (deviceId) {
          const { data: mine } = await supabase.rpc("get_season_my_rank",
            { p_start: seas.start_date, p_end: seas.end_date, p_device: deviceId });
          const m = (mine ?? [])[0];
          if (m) me = { rank: Number(m.rank), display_name: m.display_name, xp: Number(m.season_xp), capital: 0, return_pct: 0, is_ai: false };
        }
        return new Response(JSON.stringify({ success: true, type, rows, ai_total: 0, me,
          season: { season_no: seas.season_no, name: seas.name, end_date: seas.end_date } }),
          { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
      }
      // fallback: no current season → lifetime xp
      const { data } = await supabase.from("players")
        .select("display_name, level, xp, capital").gt("xp", 0)
        .order("xp", { ascending: false }).limit(limit);
      const rows = (data ?? []).map((p: any, i: number) => ({
        rank: i + 1, is_ai: false, display_name: p.display_name, level: p.level,
        xp: p.xp, capital: Number(p.capital), return_pct: retPct(Number(p.capital)),
      }));
      return new Response(JSON.stringify({ success: true, type, rows, ai_total: 0, me: null, season: null }),
        { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    // ===== RETURN BOARD (unchanged behavior) =====
    const { data, error } = await supabase.from("players")
      .select("display_name, level, xp, capital")
      .gt("xp", 0)
      .order("capital", { ascending: false }).limit(limit);
    if (error) throw error;

    type LbRow = { is_ai: boolean; display_name: string; level: number | null; xp: number | null; capital: number; return_pct: number };
    let merged: LbRow[] = (data ?? []).map((p) => ({
      is_ai: false, display_name: p.display_name, level: p.level, xp: p.xp,
      capital: Number(p.capital), return_pct: retPct(Number(p.capital)),
    }));

    const { count: rosterCount } = await supabase.from("agents")
      .select("id", { count: "exact", head: true }).or("game_roster.eq.true,game_external.eq.true");
    const aiTotal = rosterCount ?? 0;
    const { data: ags } = await supabase.from("agents")
      .select("name, game_capital").or("game_roster.eq.true,game_external.eq.true")
      .order("game_capital", { ascending: false }).limit(limit);
    const aiRows: LbRow[] = (ags ?? []).map((a) => ({
      is_ai: true, display_name: a.name, level: null, xp: null,
      capital: Number(a.game_capital), return_pct: retPct(Number(a.game_capital)),
    }));
    merged = merged.concat(aiRows).sort((x, y) => y.capital - x.capital).slice(0, limit);

    const rows = merged.map((p, i) => ({ rank: i + 1, ...p }));

    let me = null;
    if (deviceId) {
      const { data: meP } = await supabase.from("players")
        .select("display_name, capital, xp").eq("device_id", deviceId).maybeSingle();
      if (meP && Number(meP.xp) > 0) {
        const cap = Number(meP.capital);
        const { count: betterPlayers } = await supabase.from("players")
          .select("id", { count: "exact", head: true }).gt("xp", 0).gt("capital", cap);
        const { count: betterAgents } = await supabase.from("agents")
          .select("id", { count: "exact", head: true }).or("game_roster.eq.true,game_external.eq.true").gt("game_capital", cap);
        me = { rank: (betterPlayers ?? 0) + (betterAgents ?? 0) + 1, display_name: meP.display_name, capital: cap, return_pct: retPct(cap), is_ai: false };
      }
    }

    return new Response(JSON.stringify({ success: true, type, rows, ai_total: aiTotal, me, season: null }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-leaderboard error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
