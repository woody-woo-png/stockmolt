import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

// Answer key — must match WEEKEND_QUIZ[i].a in index.html (same order, 0-indexed)
const ANSWER_KEY: boolean[] = [
  true,  // 0: Apple founded 1976
  false, // 1: NYSE not 24 hours
  true,  // 2: Amazon started as bookstore
  true,  // 3: S&P 500 tracks 500 companies
  true,  // 4: Tesla added to S&P 500 in 2020
  false, // 5: Microsoft NOT founded by Gates & Jobs (Gates & Allen)
  true,  // 6: Nasdaq heavily tech-weighted
  false, // 7: Short = profit when price FALLS, not rises
  true,  // 8: Berkshire Hathaway led by Buffett
  false, // 9: Dow tracks 30 stocks, not 500
  true,  // 10: Google parent = Alphabet
  false, // 11: Bull market = prices RISING, not falling
  true,  // 12: 2008 crisis triggered partly by housing market collapse
  true,  // 13: Facebook founded 2004
  true,  // 14: Bitcoin created by Satoshi Nakamoto
  true,  // 15: Tesla ticker is TSLA
  false, // 16: P/E above 0 does NOT mean losing money
  true,  // 17: Nasdaq HQ in New York City
  true,  // 18: Berkshire has never paid a cash dividend
  true,  // 19: NVIDIA known for GPUs
  true,  // 20: IPO = Initial Public Offering
  false, // 21: US markets NOT open on Christmas
  true,  // 22: Amazon acquired Whole Foods 2017
  false, // 23: ETFs CAN be traded throughout the day (unlike mutual funds)
  true,  // 24: Apple first US company to reach $1T market cap (2018)
  true,  // 25: Federal Reserve sets US interest rates
  true,  // 26: Netflix started as DVD-by-mail
  true,  // 27: Dividend = money paid to shareholders
  true,  // 28: Elon Musk acquired Twitter 2022, rebranded to X
  true,  // 29: Nasdaq founded 1971
  false, // 30: Inflation = purchasing power DECREASING
  true,  // 31: Microsoft acquired LinkedIn 2016
  false, // 32: Blue Chip = large, stable companies — NOT high-risk startups
  true,  // 33: Gold = safe-haven asset
  true,  // 34: Jeff Bezos stepped down as Amazon CEO 2021
  true,  // 35: Market cap = share price × shares outstanding
  true,  // 36: Meta = parent of Instagram and WhatsApp
  true,  // 37: US stock market opens at 9:30 AM ET
  false, // 38: Shorting = betting price will GO DOWN
  true,  // 39: Apple App Store launched 2008
  false, // 40: Warren Buffett known for LONG-TERM investing, not day trading
  true,  // 41: Dot-com bubble burst around 2000
  false, // 42: Bond = DEBT instrument, not equity/ownership
  true,  // 43: Microsoft cloud platform = Azure
  true,  // 44: S&P 500 created in 1957
  false, // 45: SpaceX is NOT publicly traded (private company)
  false, // 46: Stock split does NOT change total value of holdings
  false, // 47: AWS launched in 2006, Amazon retail in 1994 — retail was first
  true,  // 48: "Buy low, sell high" is a basic investing principle
  true,  // 49: GameStop surged due to Reddit short squeeze in 2021
];

// LCG seed — identical algorithm must be used in index.html
function weekendQuizIndices(dateStr: string): number[] {
  let seed = parseInt(dateStr.replace(/-/g, ""), 10);
  const indices: number[] = [];
  while (indices.length < 5) {
    seed = ((seed * 1664525 + 1013904223) & 0xffffffff) >>> 0;
    const idx = seed % 50;
    if (!indices.includes(idx)) indices.push(idx);
  }
  return indices;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const { device_id, answers } = await req.json();

    if (!device_id || !Array.isArray(answers) || answers.length !== 5) {
      return new Response(
        JSON.stringify({ success: false, error: "device_id and answers[5] required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
    );

    const { data: player, error: playerErr } = await supabase
      .from("players")
      .select("id, xp, weekend_coins, last_weekend_quiz_date")
      .eq("device_id", device_id)
      .single();

    if (playerErr || !player) {
      return new Response(
        JSON.stringify({ success: false, error: "Player not found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const todayUtc = new Date().toISOString().slice(0, 10);

    // Early check (non-atomic, fast path)
    if (player.last_weekend_quiz_date === todayUtc) {
      return new Response(
        JSON.stringify({ success: false, error: "Already submitted today" }),
        { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const indices = weekendQuizIndices(todayUtc);
    const correct = indices.map((qi, i) => Boolean(answers[i]) === ANSWER_KEY[qi]);
    const score = correct.filter(Boolean).length;

    const xp_earned = score * 5;
    const coins_earned = score + (score === 5 ? 3 : 0);

    const newXp = Number(player.xp) + xp_earned;
    const newCoins = Number(player.weekend_coins) + coins_earned;

    // Atomic compare-and-swap: only update if not already submitted today
    // Use .or() because PostgREST .neq() does NOT match NULL rows
    const { data: updated, error: updateErr } = await supabase
      .from("players")
      .update({
        xp: newXp,
        weekend_coins: newCoins,
        last_weekend_quiz_date: todayUtc,
      })
      .eq("id", player.id)
      .or(`last_weekend_quiz_date.is.null,last_weekend_quiz_date.neq.${todayUtc}`)
      .select("id");

    if (updateErr) throw updateErr;

    if (!updated || updated.length === 0) {
      return new Response(
        JSON.stringify({ success: false, error: "Already submitted today" }),
        { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    return new Response(
      JSON.stringify({
        success: true,
        score,
        xp_earned,
        coins_earned,
        correct,
        total_weekend_coins: newCoins,
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("weekend-quiz-submit error:", err);
    return new Response(
      JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
