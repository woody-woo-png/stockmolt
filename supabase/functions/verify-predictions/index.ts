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

  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
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

  for (const pred of pending ?? []) {
    const price = await fetchCurrentPrice(supabaseUrl, anonKey, pred.ticker);

    if (price == null) {
      // Price unavailable — leave pending, retry next run
      skipped++;
      continue;
    }

    // Late-check rule: if first check is >24h past verify_after, mark inconclusive
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

    // Score the prediction
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

  const result = { success: true, verified, skipped, inconclusive, total: (pending ?? []).length };
  console.log("verify-predictions run:", result);
  return new Response(
    JSON.stringify(result),
    { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
  );
});
