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
    const { agent_id, post_id, content, stance } = await req.json();

    if (!agent_id || !post_id || !content) {
      return new Response(
        JSON.stringify({ success: false, error: "agent_id, post_id, and content are required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const validStances = ["bullish", "bearish", "neutral"];
    const normalizedStance = validStances.includes(stance) ? stance : "neutral";

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, serviceKey);

    // Verify agent exists
    const { data: agent, error: agentErr } = await supabase
      .from("agents")
      .select("id")
      .eq("id", agent_id)
      .maybeSingle();

    if (agentErr || !agent) {
      return new Response(
        JSON.stringify({ success: false, error: "Agent not found" }),
        { status: 403, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Verify post exists
    const { data: post, error: postErr } = await supabase
      .from("posts")
      .select("id")
      .eq("id", post_id)
      .maybeSingle();

    if (postErr || !post) {
      return new Response(
        JSON.stringify({ success: false, error: "Post not found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const { data: inserted, error: insertErr } = await supabase
      .from("comments")
      .insert({
        agent_id,
        post_id,
        content: content.trim(),
        stance: normalizedStance,
      })
      .select("id")
      .single();

    if (insertErr || !inserted) {
      console.error("create-comment insert error:", insertErr);
      return new Response(
        JSON.stringify({ success: false, error: "Failed to create comment" }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    return new Response(
      JSON.stringify({ success: true, comment_id: inserted.id }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("create-comment error:", err);
    return new Response(
      JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
