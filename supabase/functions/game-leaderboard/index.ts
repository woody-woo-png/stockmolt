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

    const rows = (data ?? []).map((p, i) => ({
      rank: i + 1,
      display_name: p.display_name,
      level: p.level,
      xp: p.xp,
      capital: p.capital,
      return_pct: Math.round(((Number(p.capital) - 100000) / 100000) * 10000) / 100,
    }));

    return new Response(JSON.stringify({ success: true, type, rows }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-leaderboard error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
