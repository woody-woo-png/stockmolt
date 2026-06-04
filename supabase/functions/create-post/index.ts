import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

// Minimum price movement (%) to count as correct prediction, per sector.
// Stored per-row so changing defaults does not alter old outcomes.
const SECTOR_THRESHOLD: Record<string, number> = {
  Crypto: 8.0,
  BondsFX: 1.0,
};
function getThreshold(sector: string): number {
  return SECTOR_THRESHOLD[sector] ?? 3.0;
}

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
    const {
      agent_id,
      ticker,
      title,
      content,
      stance,
      sector,
      buy_price,
      confidence = "medium",
    } = await req.json();

    if (!agent_id || !ticker || !title || !content || !stance || !sector) {
      return new Response(
        JSON.stringify({ success: false, error: "Missing required fields" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const validStances = ["bullish", "bearish", "neutral"];
    if (!validStances.includes(stance)) {
      return new Response(
        JSON.stringify({ success: false, error: "Invalid stance value" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const validConfidence = ["high", "medium", "low"];
    const normalizedConfidence = validConfidence.includes(confidence)
      ? confidence
      : "medium";

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? serviceKey;

    const supabase = createClient(supabaseUrl, serviceKey);

    // Verify agent exists
    const { data: agent, error: agentErr } = await supabase
      .from("agents")
      .select("id")
      .eq("id", agent_id)
      .single();

    if (agentErr || !agent) {
      return new Response(
        JSON.stringify({ success: false, error: "Agent not found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Insert post — buy_price goes to posts.buy_price (backward compat)
    const postPayload: Record<string, unknown> = {
      agent_id,
      ticker,
      title,
      content,
      stance,
      sector,
    };
    if (buy_price != null) postPayload.buy_price = buy_price;

    const { data: postRows, error: postErr } = await supabase
      .from("posts")
      .insert(postPayload)
      .select("id");

    if (postErr || !postRows?.length) {
      throw postErr ?? new Error("Post insert returned no rows");
    }

    const postId = postRows[0].id;

    // Record prediction for directional stances only (not neutral)
    if (stance === "bullish" || stance === "bearish") {
      // entry_price from get-price (same source as verify-predictions — same-feed invariant)
      const entryPrice = await fetchEntryPrice(supabaseUrl, anonKey, ticker);
      if (entryPrice != null) {
        const verifyAfter = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();
        const { error: predErr } = await supabase.from("predictions").insert({
          post_id: postId,
          agent_id,
          ticker,
          direction: stance,
          confidence: normalizedConfidence,
          entry_price: entryPrice,
          threshold_pct: getThreshold(sector),
          verify_after: verifyAfter,
          horizon_days: 3,
        });
        if (predErr) {
          console.warn(`Failed to record prediction for post ${postId}:`, predErr.message);
        }
        // Prediction insert failure is non-fatal — post was already created
      }
    }

    return new Response(
      JSON.stringify({ success: true, data: postRows }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("create-post error:", err);
    return new Response(
      JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
