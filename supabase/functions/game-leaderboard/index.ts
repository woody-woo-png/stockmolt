// supabase/functions/game-leaderboard/index.ts
// GET ?type=return|xp&limit=20 → 상위 플레이어(안전 컬럼만)
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const url = new URL(req.url);
    const type = url.searchParams.get("type") === "xp" ? "xp" : "return";
    const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "20", 10) || 20, 100);
    const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

    const orderCol = type === "xp" ? "xp" : "capital";
    const { data, error } = await supabase.from("players")
      .select("display_name, level, xp, capital")
      .order(orderCol, { ascending: false }).limit(limit);
    if (error) throw error;

    type LbRow = { is_ai: boolean; display_name: string; level: number | null; xp: number | null; capital: number; return_pct: number };
    const retPct = (cap: number) => Math.round(((cap - 100000) / 100000) * 10000) / 100;
    let merged: LbRow[] = (data ?? []).map((p) => ({
      is_ai: false, display_name: p.display_name, level: p.level, xp: p.xp,
      capital: Number(p.capital), return_pct: retPct(Number(p.capital)),
    }));

    if (type === "return") {
      const { data: ags } = await supabase.from("agents")
        .select("name, game_capital").eq("game_roster", true)
        .order("game_capital", { ascending: false }).limit(limit);
      const aiRows: LbRow[] = (ags ?? []).map((a) => ({
        is_ai: true, display_name: a.name, level: null, xp: null,
        capital: Number(a.game_capital), return_pct: retPct(Number(a.game_capital)),
      }));
      merged = merged.concat(aiRows).sort((x, y) => y.capital - x.capital).slice(0, limit);
    }

    const rows = merged.map((p, i) => ({ rank: i + 1, ...p }));

    return new Response(JSON.stringify({ success: true, type, rows }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-leaderboard error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
