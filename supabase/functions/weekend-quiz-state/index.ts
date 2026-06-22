import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const { device_id } = await req.json();
    if (!device_id) {
      return new Response(
        JSON.stringify({ success: false, error: "device_id is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
    );

    const { data: player, error } = await supabase
      .from("players")
      .select("weekend_coins, last_weekend_quiz_date")
      .eq("device_id", device_id)
      .single();

    if (error || !player) {
      return new Response(
        JSON.stringify({ success: false, error: "Player not found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const todayUtc = new Date().toISOString().slice(0, 10); // "YYYY-MM-DD"
    const submittedToday = player.last_weekend_quiz_date === todayUtc;

    return new Response(
      JSON.stringify({
        success: true,
        weekend_coins: player.weekend_coins ?? 0,
        last_weekend_quiz_date: player.last_weekend_quiz_date ?? null,
        submitted_today: submittedToday,
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("weekend-quiz-state error:", err);
    return new Response(
      JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
