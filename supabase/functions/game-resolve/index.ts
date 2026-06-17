// supabase/functions/game-resolve/index.ts
// POST (cron) — 미판정 과거 풀(trade_date < 오늘)을 exit 시세로 판정.
// 픽/AI콜 판정 → 플레이어 일일집계(game_daily_result) → XP/레벨/스트릭/자산 갱신. 멱등.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { avg, computeReturnPct, isCorrect, levelFromXp, nextStreak, resultXp } from "../_shared/game_logic.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};
const todayUtc = () => new Date().toISOString().slice(0, 10);

async function getPrice(supabaseUrl: string, anonKey: string, ticker: string): Promise<number | null> {
  try {
    const res = await fetch(`${supabaseUrl}/functions/v1/get-price?ticker=${encodeURIComponent(ticker)}`,
      { headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` } });
    const data = await res.json();
    return typeof data.price === "number" ? data.price : null;
  } catch (_) { return null; }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? serviceKey;
    const supabase = createClient(supabaseUrl, serviceKey);
    const today = todayUtc();

    // 당일 완결: 마감(20:00 UTC, EDT) 지난 오늘 풀까지 정산. cron이 20:30 UTC라 오늘 세션은 이미 마감.
    // 장중(마감 전)이면 오늘 풀은 절대 건드리지 않고 과거 미정산분만 정산.
    const nowUtc = new Date();
    const closeUtc = new Date(`${today}T20:00:00Z`);
    const sessionClosed = nowUtc >= closeUtc;
    const cutoff = sessionClosed ? today : new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    const { data: pools } = await supabase.from("game_ticker_pool")
      .select("trade_date").eq("resolved", false).lte("trade_date", cutoff);
    const dates = [...new Set((pools ?? []).map((r) => r.trade_date))].sort();
    const resolvedDates: string[] = [];

    for (const tradeDate of dates) {
      const { data: poolRows } = await supabase.from("game_ticker_pool")
        .select("ticker, entry_price, exit_price").eq("trade_date", tradeDate);
      const priceMap: Record<string, { entry: number; exit: number }> = {};
      for (const r of poolRows ?? []) {
        if (r.entry_price == null) continue;
        let exit = r.exit_price;
        if (exit == null) {
          exit = await getPrice(supabaseUrl, anonKey, r.ticker);
          if (exit != null) {
            await supabase.from("game_ticker_pool")
              .update({ exit_price: exit, exit_price_at: new Date().toISOString(), resolved: true })
              .eq("trade_date", tradeDate).eq("ticker", r.ticker);
          }
        }
        if (exit != null) priceMap[r.ticker] = { entry: Number(r.entry_price), exit: Number(exit) };
      }
      if (Object.keys(priceMap).length === 0) continue;

      const { data: picks } = await supabase.from("game_pick")
        .select("id, player_id, ticker, direction, resolved").eq("trade_date", tradeDate);
      for (const pk of picks ?? []) {
        if (pk.resolved) continue;
        const pm = priceMap[pk.ticker];
        if (!pm) continue;
        const ret = computeReturnPct(pk.direction, pm.entry, pm.exit);
        await supabase.from("game_pick")
          .update({ return_pct: ret, correct: isCorrect(ret), resolved: true }).eq("id", pk.id);
      }

      const { data: aiPicks } = await supabase.from("game_ai_pick")
        .select("id, agent_id, ticker, direction, return_pct").eq("trade_date", tradeDate);
      const aiReturnByTicker: Record<string, number> = {};
      for (const ap of aiPicks ?? []) {
        const pm = priceMap[ap.ticker];
        if (!pm) continue;
        const ret = computeReturnPct(ap.direction, pm.entry, pm.exit);
        aiReturnByTicker[ap.ticker] = ret;
        if (ap.return_pct == null) {
          await supabase.from("game_ai_pick")
            .update({ return_pct: ret, correct: isCorrect(ret) }).eq("id", ap.id);
        }
      }

      const { data: rivalRow } = await supabase.from("game_daily_rival")
        .select("agent_id").eq("trade_date", tradeDate).maybeSingle();
      const rivalAgentId = rivalRow?.agent_id ?? null;

      const { data: prevPool } = await supabase.from("game_ticker_pool")
        .select("trade_date").lt("trade_date", tradeDate).order("trade_date", { ascending: false }).limit(1).maybeSingle();
      const prevTradeDate = prevPool?.trade_date ?? null;

      const picksByPlayer: Record<string, { ticker: string; direction: string }[]> = {};
      const { data: allPicks } = await supabase.from("game_pick")
        .select("player_id, ticker, direction").eq("trade_date", tradeDate);
      for (const p of allPicks ?? []) {
        (picksByPlayer[p.player_id] ??= []).push({ ticker: p.ticker, direction: p.direction });
      }

      for (const [playerId, plist] of Object.entries(picksByPlayer)) {
        const { data: existed } = await supabase.from("game_daily_result")
          .select("id").eq("player_id", playerId).eq("trade_date", tradeDate).maybeSingle();
        if (existed) continue;

        const userReturns = plist.map((p) => {
          const pm = priceMap[p.ticker];
          return pm ? computeReturnPct(p.direction as "long" | "short", pm.entry, pm.exit) : 0;
        });
        const userAvg = avg(userReturns);
        const correctCount = userReturns.filter(isCorrect).length;
        const rivalReturns = plist.map((p) => aiReturnByTicker[p.ticker]).filter((x) => x != null) as number[];
        const rivalAvg = rivalReturns.length ? avg(rivalReturns) : null;
        const beatAi = rivalAvg != null && userAvg > rivalAvg;

        let playedPrev = false;
        if (prevTradeDate) {
          const { data: prevRes } = await supabase.from("game_daily_result")
            .select("id").eq("player_id", playerId).eq("trade_date", prevTradeDate).maybeSingle();
          playedPrev = !!prevRes;
        }
        const { data: player } = await supabase.from("players")
          .select("xp, capital, streak_current, streak_best").eq("id", playerId).single();
        const newStreak = nextStreak(player!.streak_current, playedPrev);
        const { total: xpEarned, breakdown } = resultXp({ correctCount, beatAi, newStreak });

        const capitalBefore = Number(player!.capital);
        const capitalAfter = Math.round(capitalBefore * (1 + userAvg / 100) * 100) / 100;

        await supabase.from("game_daily_result").insert({
          player_id: playerId, trade_date: tradeDate, picks_count: plist.length,
          avg_return_pct: Math.round(userAvg * 100) / 100, correct_count: correctCount,
          win_rate_daily: Math.round((correctCount / plist.length) * 10000) / 100,
          capital_before: capitalBefore, capital_after: capitalAfter, xp_earned: xpEarned,
          beat_ai: beatAi, ai_agent_id: rivalAgentId, ai_avg_return_pct: rivalAvg,
        });

        for (const b of breakdown) {
          await supabase.from("game_xp_ledger")
            .insert({ player_id: playerId, trade_date: tradeDate, reason: b.reason, xp_delta: b.xp });
        }

        const newXp = player!.xp + xpEarned;
        await supabase.from("players").update({
          xp: newXp, level: levelFromXp(newXp), capital: capitalAfter,
          streak_current: newStreak, streak_best: Math.max(player!.streak_best, newStreak),
          last_played_date: tradeDate,
        }).eq("id", playerId);
      }
      // === 로스터 에이전트 채점 + game_capital 복리 (standings) — priceMap 재사용, 멱등.
      // 사람 판정 경로와 런타임 격리: 이 블록에서 throw해도 사람 결과/날짜 완료(resolvedDates)에 영향 없게 전체를 try로 감싸고,
      // 에이전트별로도 try로 감싸 한 에이전트의 실패가 나머지를 건너뛰지 않게 함. (에러는 로깅만)
      try {
        const { data: agentPicks } = await supabase.from("game_agent_pick")
          .select("id, agent_id, ticker, direction, resolved").eq("trade_date", tradeDate);
        const picksByAgent: Record<string, { ticker: string; direction: string }[]> = {};
        for (const ap of agentPicks ?? []) {
          try {
            if (!ap.resolved) {
              const pm = priceMap[ap.ticker];
              if (pm) {
                const ret = computeReturnPct(ap.direction as "long" | "short", pm.entry, pm.exit);
                await supabase.from("game_agent_pick")
                  .update({ return_pct: ret, correct: isCorrect(ret), resolved: true }).eq("id", ap.id);
              }
            }
          } catch (e) { console.error("agent pick resolve error", ap.id, e); }
          (picksByAgent[ap.agent_id] ??= []).push({ ticker: ap.ticker, direction: ap.direction });
        }
        for (const [agentId, aplist] of Object.entries(picksByAgent)) {
          try {
            const { data: existedA } = await supabase.from("game_agent_result")
              .select("id").eq("agent_id", agentId).eq("trade_date", tradeDate).maybeSingle();
            if (existedA) continue;
            const aReturns = aplist.map((p) => {
              const pm = priceMap[p.ticker];
              return pm ? computeReturnPct(p.direction as "long" | "short", pm.entry, pm.exit) : 0;
            });
            const aAvg = avg(aReturns);
            const aCorrect = aReturns.filter(isCorrect).length;
            const { data: agRow } = await supabase.from("agents").select("game_capital").eq("id", agentId).single();
            const capBefore = Number(agRow!.game_capital);
            const capAfter = Math.round(capBefore * (1 + aAvg / 100) * 100) / 100;
            await supabase.from("game_agent_result").insert({
              agent_id: agentId, trade_date: tradeDate,
              avg_return_pct: Math.round(aAvg * 100) / 100, correct_count: aCorrect,
              capital_before: capBefore, capital_after: capAfter,
            });
            await supabase.from("agents")
              .update({ game_capital: capAfter, game_updated_at: new Date().toISOString() }).eq("id", agentId);
          } catch (e) { console.error("agent standings error", agentId, e); }
        }
      } catch (e) { console.error("roster standings block error", tradeDate, e); }
      resolvedDates.push(tradeDate);
    }

    return new Response(JSON.stringify({ success: true, resolved_dates: resolvedDates }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-resolve error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
