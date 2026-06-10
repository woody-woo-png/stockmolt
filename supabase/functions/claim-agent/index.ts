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
    const { agent_id, claim_token, owner_name, owner_handle } = await req.json();

    if (!agent_id || !owner_name?.trim()) {
      return new Response(
        JSON.stringify({ success: false, error: "agent_id and owner_name are required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, serviceKey);

    const { data: agent, error: findErr } = await supabase
      .from("agents")
      .select("id, claim_token, claimed_at")
      .eq("id", agent_id)
      .maybeSingle();

    if (findErr || !agent) {
      return new Response(
        JSON.stringify({ success: false, error: "Agent not found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Verify token if agent has one set (empty string or null = no token required)
    if (agent.claim_token && claim_token !== agent.claim_token) {
      return new Response(
        JSON.stringify({ success: false, error: "Invalid claim token" }),
        { status: 403, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const { error: updateErr } = await supabase
      .from("agents")
      .update({
        owner_name: owner_name.trim().slice(0, 80),
        owner_handle: (owner_handle || owner_name).trim().slice(0, 80),
        claimed_at: new Date().toISOString(),
      })
      .eq("id", agent_id);

    if (updateErr) throw updateErr;

    return new Response(
      JSON.stringify({ success: true }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("claim-agent error:", err);
    return new Response(
      JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
