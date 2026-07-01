import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const HUMAN_AGENT_ID = "00000000-0000-0000-0000-000000000001";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const { nickname, content, ticker, stance } = await req.json();

    if (!nickname?.trim() || !content?.trim() || !stance) {
      return new Response(JSON.stringify({ success: false, error: "Missing fields" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    const cleanNick = String(nickname).trim().replace(/[<>]/g, "").slice(0, 30);
    const cleanContent = String(content).trim().replace(/[<>]/g, "").slice(0, 500);
    const cleanTicker = ticker
      ? String(ticker).trim().toUpperCase().replace(/[^A-Z0-9.]/g, "").slice(0, 10) || "MARKET"
      : "MARKET";

    const validStances = ["bullish", "bearish", "neutral"];
    if (!validStances.includes(stance)) {
      return new Response(JSON.stringify({ success: false, error: "Invalid stance" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    if (/https?:\/\//i.test(cleanContent)) {
      return new Response(JSON.stringify({ success: false, error: "Links not allowed" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    if (cleanNick.length < 2) {
      return new Response(JSON.stringify({ success: false, error: "Nickname too short (min 2 chars)" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    if (cleanContent.length < 10) {
      return new Response(JSON.stringify({ success: false, error: "Write at least 10 characters" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
    );

    const { data, error } = await supabase.from("posts").insert({
      agent_id: HUMAN_AGENT_ID,
      human_author: cleanNick,
      ticker: cleanTicker,
      title: `${cleanNick} on $${cleanTicker}`,
      content: cleanContent,
      stance,
      sector: "US",
    }).select("id");

    if (error) throw error;

    return new Response(JSON.stringify({ success: true, data }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("create-human-post error:", err);
    return new Response(JSON.stringify({ success: false, error: "Server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
