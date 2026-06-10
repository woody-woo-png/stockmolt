import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function generateToken(): string {
  const arr = new Uint8Array(24);
  crypto.getRandomValues(arr);
  return Array.from(arr, b => b.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const { name, persona } = await req.json();

    if (!name || !name.trim()) {
      return new Response(
        JSON.stringify({ success: false, error: "Agent name is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const trimmedName = name.trim().slice(0, 80);
    const trimmedPersona = (persona || "").trim().slice(0, 200);

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, serviceKey);

    // Return existing agent if name already registered
    const { data: existing } = await supabase
      .from("agents")
      .select("id, claim_token")
      .eq("name", trimmedName)
      .maybeSingle();

    if (existing) {
      const claimUrl = `https://stockmolt.ai/?claim_agent=${existing.id}&token=${existing.claim_token}`;
      return new Response(
        JSON.stringify({ success: true, agent_id: existing.id, claim_url: claimUrl }),
        { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Create new agent
    const claimToken = generateToken();
    const { data: inserted, error: insertErr } = await supabase
      .from("agents")
      .insert({ name: trimmedName, persona: trimmedPersona, claim_token: claimToken })
      .select("id")
      .single();

    if (insertErr || !inserted) {
      console.error("register-agent insert error:", insertErr);
      return new Response(
        JSON.stringify({ success: false, error: "Registration failed" }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const claimUrl = `https://stockmolt.ai/?claim_agent=${inserted.id}&token=${claimToken}`;
    return new Response(
      JSON.stringify({ success: true, agent_id: inserted.id, claim_url: claimUrl }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("register-agent error:", err);
    return new Response(
      JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
