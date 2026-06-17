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

    const { data: season } = await supabase.from("game_seasons")
      .select("season_no, name, end_date").lte("start_date", today).gte("end_date", today).maybeSingle();
    let current_season = null;
    if (season) {
      const ends = Math.max(0, Math.ceil(
        (new Date(season.end_date + "T00:00:00Z").getTime() - new Date(today + "T00:00:00Z").getTime()) / 86400000));
      current_season = { season_no: season.season_no, name: season.name, end_date: season.end_date, ends_in_days: ends };
    }
    const { data: prestigeRows } = await supabase.from("game_prestige")
      .select("season_no").eq("player_id", player.id).order("season_no", { ascending: true });
    const prestige = (prestigeRows ?? []).map((r: any) => r.season_no);
    const { data: awardRows } = await supabase.from("game_season_award")
      .select("season_no, tier").eq("player_id", player.id).order("season_no", { ascending: true });
    const season_awards = (awardRows ?? []).map((r: any) => ({ season_no: r.season_no, tier: r.tier }));
    const safePlayer = {
      id: player.id, display_name: player.display_name, level: player.level, xp: player.xp,
      streak_current: player.streak_current, streak_best: player.streak_best,
      capital: player.capital, claimed: player.claimed, prestige, season_awards,
    };

    return new Response(JSON.stringify({
      success: true,
      player: safePlayer,
      submitted_today: (pickCount ?? 0) > 0,
      last_result: lastResult ?? null,
      current_season,
    }), { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-state error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
