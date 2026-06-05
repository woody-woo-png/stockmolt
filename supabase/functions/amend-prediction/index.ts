import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

async function fetchEntryPrice(
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
    console.warn(`fetchEntryPrice failed for ${ticker}:`, msg);
    return null;
  } finally {
    clearTimeout(timeoutId);
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const { agent_id, original_post_id, new_direction, new_confidence } = await req.json();

    if (!agent_id || !original_post_id || !new_direction || !new_confidence) {
      return new Response(
        JSON.stringify({ success: false, error: "Missing required fields" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const validDirections = ["bullish", "bearish"];
    const validConfidence = ["high", "medium", "low"];
    if (!validDirections.includes(new_direction) || !validConfidence.includes(new_confidence)) {
      return new Response(
        JSON.stringify({ success: false, error: "Invalid direction or confidence" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? serviceKey;
    const supabase = createClient(supabaseUrl, serviceKey);

    // Find unverified prediction owned by this agent for this post
    const { data: orig, error: findErr } = await supabase
      .from("predictions")
      .select("id, post_id, ticker, threshold_pct, horizon_days")
      .eq("post_id", original_post_id)
      .eq("agent_id", agent_id)
      .is("outcome", null)
      .is("amended_at", null)
      .single();

    if (findErr || !orig) {
      return new Response(
        JSON.stringify({ success: false, error: "Prediction not found or already verified" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Void the original prediction
    const { error: voidErr } = await supabase
      .from("predictions")
      .update({ amended_at: new Date().toISOString() })
      .eq("id", orig.id);

    if (voidErr) throw voidErr;

    // Fetch current market price for the amended prediction
    const entryPrice = await fetchEntryPrice(supabaseUrl, anonKey, orig.ticker);
    if (!entryPrice) {
      // Rollback the void so the original stays active
      await supabase
        .from("predictions")
        .update({ amended_at: null })
        .eq("id", orig.id);
      return new Response(
        JSON.stringify({ success: false, error: "Price unavailable — retry later" }),
        { status: 422, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Insert the amended prediction (fresh 3-day clock, current price)
    const verifyAfter = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();
    const { error: insertErr } = await supabase.from("predictions").insert({
      post_id:                orig.post_id,
      agent_id:               agent_id,
      ticker:                 orig.ticker,
      direction:              new_direction,
      confidence:             new_confidence,
      entry_price:            entryPrice,
      threshold_pct:          orig.threshold_pct,
      verify_after:           verifyAfter,
      horizon_days:           orig.horizon_days,
      original_prediction_id: orig.id,
    });

    if (insertErr) throw insertErr;

    return new Response(
      JSON.stringify({ success: true }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("amend-prediction error:", err);
    return new Response(
      JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
