// supabase/functions/game-state/index.ts
// POST { device_id, display_name? } → player + 오늘 픽 여부 + 직전 미확인 결과
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function todayUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const { device_id, display_name } = await req.json();
    if (!device_id || typeof device_id !== "string") {
      return new Response(JSON.stringify({ success: false, error: "Missing device_id" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }
    const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

    let { data: player } = await supabase.from("players").select("*").eq("device_id", device_id).maybeSingle();
    if (!player) {
      const name = (typeof display_name === "string" && display_name.trim()) ? display_name.trim().slice(0, 24)
        : `Trader-${device_id.slice(0, 6)}`;
      const { data: created, error: insErr } = await supabase.from("players")
        .insert({ device_id, display_name: name }).select("*").single();
      if (insErr) throw insErr;
      player = created;
    }

    const today = todayUtc();
    const { count: pickCount } = await supabase.from("game_pick")
      .select("id", { count: "exact", head: true })
      .eq("player_id", player.id).eq("trade_date", today);

    const { data: lastResult } = await supabase.from("game_daily_result")
      .select("*").eq("player_id", player.id).order("trade_date", { ascending: false }).limit(1).maybeSingle();

    const safePlayer = {
      id: player.id, display_name: player.display_name, level: player.level, xp: player.xp,
      streak_current: player.streak_current, streak_best: player.streak_best,
      capital: player.capital, claimed: player.claimed,
    };

    return new Response(JSON.stringify({
      success: true,
      player: safePlayer,
      submitted_today: (pickCount ?? 0) > 0,
      last_result: lastResult ?? null,
    }), { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-state error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
