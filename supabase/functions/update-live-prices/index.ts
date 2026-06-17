// supabase/functions/update-live-prices/index.ts
// Live-price cache for the same-day loop. Called by cron every ~2 min during the
// regular session (13:30-20:00 UTC). For today's pool, fetch each ticker's current
// price via get-price and write live_price/live_price_at. One set of provider calls
// regardless of how many users are watching. Reusable engine for phases B/C.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};
const todayUtc = () => new Date().toISOString().slice(0, 10);

async function getPrice(url: string, key: string, ticker: string): Promise<number | null> {
  try {
    const r = await fetch(`${url}/functions/v1/get-price?ticker=${encodeURIComponent(ticker)}`,
      { headers: { apikey: key, Authorization: `Bearer ${key}` } });
    const d = await r.json();
    return typeof d.price === "number" ? d.price : null;
  } catch (_) {
    return null;
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const url = Deno.env.get("SUPABASE_URL")!;
    const service = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const anon = Deno.env.get("SUPABASE_ANON_KEY") ?? service;
    const supabase = createClient(url, service);
    const today = todayUtc();

    const { data: pool } = await supabase.from("game_ticker_pool").select("ticker").eq("trade_date", today);
    let updated = 0;
    for (const row of pool ?? []) {
      const p = await getPrice(url, anon, row.ticker);
      if (p != null) {
        await supabase.from("game_ticker_pool")
          .update({ live_price: p, live_price_at: new Date().toISOString() })
          .eq("trade_date", today).eq("ticker", row.ticker);
        updated++;
      }
    }
    return new Response(JSON.stringify({ success: true, updated }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("update-live-prices error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
