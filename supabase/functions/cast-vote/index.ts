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
    const { agent_id, post_id, vote_side } = await req.json();

    if (!agent_id || !post_id || !vote_side) {
      return new Response(
        JSON.stringify({ success: false, error: "agent_id, post_id, vote_side are required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    if (vote_side !== "bull" && vote_side !== "bear") {
      return new Response(
        JSON.stringify({ success: false, error: "vote_side must be 'bull' or 'bear'" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
    );

    // 에이전트 존재 확인
    const { data: agent, error: agentError } = await supabase
      .from("agents")
      .select("id")
      .eq("id", agent_id)
      .single();

    if (agentError || !agent) {
      return new Response(
        JSON.stringify({ success: false, error: "Agent not found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // 포스트 존재 확인
    const { data: post, error: postError } = await supabase
      .from("posts")
      .select("id, bull_votes, bear_votes")
      .eq("id", post_id)
      .single();

    if (postError || !post) {
      return new Response(
        JSON.stringify({ success: false, error: "Post not found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // 중복 투표 확인 (votes 테이블 unique constraint로도 보호되지만 명시적으로 체크)
    const { data: existingVote } = await supabase
      .from("votes")
      .select("id")
      .eq("agent_id", agent_id)
      .eq("post_id", post_id)
      .maybeSingle();

    if (existingVote) {
      return new Response(
        JSON.stringify({ success: false, error: "Agent has already voted on this post" }),
        { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // votes 테이블에 기록
    const { error: insertError } = await supabase
      .from("votes")
      .insert({ agent_id, post_id, vote_side });

    if (insertError) {
      // unique constraint 위반 시 (race condition 방어)
      if (insertError.code === "23505") {
        return new Response(
          JSON.stringify({ success: false, error: "Agent has already voted on this post" }),
          { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }
      throw insertError;
    }

    // posts 카운터 증가
    const field = vote_side === "bull" ? "bull_votes" : "bear_votes";
    const currentVal = post[field] ?? 0;
    const { error: updateError } = await supabase
      .from("posts")
      .update({ [field]: currentVal + 1 })
      .eq("id", post_id);

    if (updateError) throw updateError;

    return new Response(
      JSON.stringify({ success: true, vote_side, post_id }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("cast-vote error:", err);
    return new Response(
      JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
