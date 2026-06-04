import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

// If first successful price check is >24h past verify_after, mark inconclusive.
// Prevents weekend market closures (T+3 lands Saturday → first check Monday = T+5)
// from being scored against an off-day price.
const MAX_LATE_HOURS = 24;

async function fetchCurrentPrice(
  supabaseUrl: string,
  anonKey: string,
  ticker: string
): Promise<number | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);
  try {
    const res = await fetch(
      `${supabaseUrl}/functions/v1/get-price?ticker=${encodeURIComponent(ticker)}`,
      { headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` }, signal: controller.signal }
    );
    const data = await res.json();
    return data.price ?? null;
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.warn(`fetchCurrentPrice failed for ${ticker}:`, msg);
    return null;
  } finally {
    clearTimeout(timeoutId);
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  // Only allow calls from Supabase cron (service role key required)
  const authHeader = req.headers.get("Authorization");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  if (!authHeader || authHeader !== `Bearer ${serviceKey}`) {
    return new Response(
      JSON.stringify({ success: false, error: "Unauthorized" }),
      { status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? serviceKey;
  const supabase = createClient(supabaseUrl, serviceKey);

  const now = new Date();

  // Fetch all unverified predictions whose verify_after has passed
  const { data: pending, error } = await supabase
    .from("predictions")
    .select("id, ticker, direction, entry_price, threshold_pct, verify_after")
    .is("outcome", null)
    .lte("verify_after", now.toISOString());

  if (error) {
    console.error("fetch pending error:", error);
    return new Response(
      JSON.stringify({ success: false, error: error.message }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }

  let verified = 0, skipped = 0, inconclusive = 0;
  const pendingRows = pending ?? [];

  // Deduplicate tickers and fetch all prices in parallel
  const uniqueTickers = [...new Set(pendingRows.map(p => p.ticker))];
  const priceResults = await Promise.all(
    uniqueTickers.map(async ticker => ({
      ticker,
      price: await fetchCurrentPrice(supabaseUrl, anonKey, ticker),
    }))
  );
  const priceMap: Record<string, number | null> = {};
  for (const { ticker, price } of priceResults) {
    priceMap[ticker] = price;
  }

  for (const pred of pendingRows) {
    const price = priceMap[pred.ticker] ?? null;

    if (price == null) {
      skipped++;
      continue;
    }

    if (pred.entry_price == null || pred.entry_price === 0) {
      console.warn(`Skipping prediction ${pred.id}: invalid entry_price ${pred.entry_price}`);
      skipped++;
      continue;
    }

    const verifyAfterMs = new Date(pred.verify_after).getTime();
    const lateHours = (now.getTime() - verifyAfterMs) / (1000 * 60 * 60);
    if (lateHours > MAX_LATE_HOURS) {
      const { error: updateErr } = await supabase
        .from("predictions")
        .update({ outcome: "inconclusive", outcome_price: price, outcome_checked_at: now.toISOString() })
        .eq("id", pred.id);
      if (updateErr) console.warn(`Failed to mark inconclusive for ${pred.id}:`, updateErr.message);
      else inconclusive++;
      continue;
    }

    const changePct = ((price - pred.entry_price) / pred.entry_price) * 100;
    let outcome: "correct" | "incorrect";
    if (pred.direction === "bullish") {
      outcome = changePct >= pred.threshold_pct ? "correct" : "incorrect";
    } else {
      outcome = changePct <= -pred.threshold_pct ? "correct" : "incorrect";
    }

    const { error: updateErr } = await supabase
      .from("predictions")
      .update({ outcome, outcome_price: price, outcome_checked_at: now.toISOString() })
      .eq("id", pred.id);
    if (updateErr) {
      console.warn(`Failed to update prediction ${pred.id}:`, updateErr.message);
    } else {
      verified++;
    }
  }

  const result = { success: true, verified, skipped, inconclusive, total: pendingRows.length };
  console.log("verify-predictions run:", result);
  return new Response(
    JSON.stringify(result),
    { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
  );
});
