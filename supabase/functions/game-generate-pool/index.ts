// supabase/functions/game-generate-pool/index.ts
// POST (cron) — 오늘 6종목 풀 생성, entry 시세 채움, 라이벌 AI 선정, AI 6콜 생성.
// 멱등: 이미 오늘 풀이 있으면 종목 생성은 건너뛰고 누락 보강만.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};
const todayUtc = () => new Date().toISOString().slice(0, 10);

const US_UNIVERSE = ["NVDA","AAPL","TSLA","MSFT","META","GOOGL","AMZN","AMD","COIN","PLTR","NFLX","AVGO"];

function pickSix(seed: number): string[] {
  const arr = [...US_UNIVERSE];
  for (let i = arr.length - 1; i > 0; i--) {
    seed = (seed * 9301 + 49297) % 233280;
    const j = Math.floor((seed / 233280) * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr.slice(0, 6);
}

async function getPrice(supabaseUrl: string, anonKey: string, ticker: string): Promise<number | null> {
  try {
    const res = await fetch(`${supabaseUrl}/functions/v1/get-price?ticker=${encodeURIComponent(ticker)}`,
      { headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` } });
    const data = await res.json();
    return typeof data.price === "number" ? data.price : null;
  } catch (_) { return null; }
}

async function getAiCalls(tickers: { ticker: string; entry: number }[]): Promise<Record<string, "long" | "short"> | null> {
  const groqKey = Deno.env.get("GROQ_API_KEY");
  if (!groqKey) return null;
  const list = tickers.map((t) => `${t.ticker} @ $${t.entry}`).join(", ");
  const prompt = `You are a stock trader. For each ticker, decide LONG or SHORT for the next trading day based on the price.
Tickers: ${list}.
Respond ONLY as compact JSON mapping ticker to "long" or "short". Example: {"NVDA":"long","AAPL":"short"}`;
  try {
    const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${groqKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "llama-3.3-70b-versatile", temperature: 0.4, max_tokens: 200,
        messages: [{ role: "user", content: prompt }] }),
    });
    const data = await res.json();
    const raw = data?.choices?.[0]?.message?.content ?? "";
    const clean = raw.replace(/```json/g, "").replace(/```/g, "").trim();
    const parsed = JSON.parse(clean);
    const out: Record<string, "long" | "short"> = {};
    for (const t of tickers) {
      const v = String(parsed[t.ticker] ?? "").toLowerCase();
      out[t.ticker] = v === "short" ? "short" : "long";
    }
    return out;
  } catch (_) { return null; }
}

// 로스터 에이전트용: persona로 성향을 준 뒤 6종목 중 정확히 3개를 long/short 선택. Groq 실패/오류 시 랜덤 3개 fallback.
async function getAgentPicks(persona: string, tickers: { ticker: string; entry: number }[]): Promise<{ ticker: string; direction: "long" | "short" }[]> {
  const all = tickers.map((t) => t.ticker);
  const randomThree = (): { ticker: string; direction: "long" | "short" }[] =>
    [...all].sort(() => Math.random() - 0.5).slice(0, 3)
      .map((t) => ({ ticker: t, direction: (Math.random() < 0.5 ? "long" : "short") as "long" | "short" }));
  const groqKey = Deno.env.get("GROQ_API_KEY");
  if (!groqKey) return randomThree();
  const list = tickers.map((t) => `${t.ticker} @ $${t.entry}`).join(", ");
  const prompt = `You are ${persona}\nFrom these stocks, choose EXACTLY your 3 best trades for the next trading day, each LONG or SHORT, matching your trading style.\nStocks: ${list}.\nRespond ONLY as compact JSON mapping exactly 3 of the tickers to "long" or "short". Example: {"NVDA":"long","COIN":"short","AMD":"long"}`;
  try {
    const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${groqKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "llama-3.3-70b-versatile", temperature: 0.6, max_tokens: 120,
        messages: [{ role: "user", content: prompt }] }),
    });
    const data = await res.json();
    const raw = data?.choices?.[0]?.message?.content ?? "";
    const clean = raw.replace(/```json/g, "").replace(/```/g, "").trim();
    const parsed = JSON.parse(clean);
    const picks: { ticker: string; direction: "long" | "short" }[] = [];
    for (const [tk, dir] of Object.entries(parsed)) {
      if (!all.includes(tk) || picks.find((p) => p.ticker === tk)) continue;
      picks.push({ ticker: tk, direction: String(dir).toLowerCase() === "short" ? "short" : "long" });
      if (picks.length === 3) break;
    }
    for (const t of all) {
      if (picks.length >= 3) break;
      if (!picks.find((p) => p.ticker === t)) picks.push({ ticker: t, direction: Math.random() < 0.5 ? "short" : "long" });
    }
    return picks.slice(0, 3);
  } catch (_) {
    return randomThree();
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? serviceKey;
    const supabase = createClient(supabaseUrl, serviceKey);
    const today = todayUtc();

    const { data: existing } = await supabase.from("game_ticker_pool").select("ticker, entry_price").eq("trade_date", today);
    let tickers: string[];
    if (existing && existing.length > 0) {
      tickers = existing.map((r) => r.ticker);
    } else {
      const seed = parseInt(today.replace(/-/g, ""), 10);
      tickers = pickSix(seed);
      const rows = tickers.map((t) => ({ trade_date: today, ticker: t, market: "US", sector: "US" }));
      const { error } = await supabase.from("game_ticker_pool").insert(rows);
      if (error) throw error;
    }

    const withEntry: { ticker: string; entry: number }[] = [];
    for (const t of tickers) {
      const { data: row } = await supabase.from("game_ticker_pool")
        .select("entry_price").eq("trade_date", today).eq("ticker", t).single();
      let entry = row?.entry_price ?? null;
      if (entry == null) {
        entry = await getPrice(supabaseUrl, anonKey, t);
        if (entry != null) {
          await supabase.from("game_ticker_pool")
            .update({ entry_price: entry, entry_price_at: new Date().toISOString(), price_source: "get-price" })
            .eq("trade_date", today).eq("ticker", t);
        }
      }
      if (entry != null) withEntry.push({ ticker: t, entry: Number(entry) });
    }

    let { data: rival } = await supabase.from("game_daily_rival").select("agent_id").eq("trade_date", today).maybeSingle();
    if (!rival) {
      const { data: agents } = await supabase.from("agents").select("id").order("created_at", { ascending: true }).limit(20);
      if (agents && agents.length > 0) {
        const idx = parseInt(today.replace(/-/g, ""), 10) % agents.length;
        const agentId = agents[idx].id;
        await supabase.from("game_daily_rival").insert({ trade_date: today, agent_id: agentId });
        rival = { agent_id: agentId };
      }
    }

    if (rival) {
      const { count: aiCount } = await supabase.from("game_ai_pick")
        .select("id", { count: "exact", head: true }).eq("trade_date", today).eq("agent_id", rival.agent_id);
      if ((aiCount ?? 0) === 0 && withEntry.length > 0) {
        const calls = await getAiCalls(withEntry);
        const aiRows = withEntry.map((t) => ({
          agent_id: rival!.agent_id, trade_date: today, ticker: t.ticker,
          direction: calls ? calls[t.ticker] : (Math.random() < 0.5 ? "long" : "short"),
        }));
        await supabase.from("game_ai_pick").insert(aiRows);
      }
    }

    // === 로스터 에이전트 standings 픽(3개) 생성 — 멱등 ===
    if (withEntry.length >= 3) {
      const { data: roster } = await supabase.from("agents").select("id, persona").eq("game_roster", true);
      for (const ag of roster ?? []) {
        const { count } = await supabase.from("game_agent_pick")
          .select("id", { count: "exact", head: true }).eq("trade_date", today).eq("agent_id", ag.id);
        if ((count ?? 0) > 0) continue;
        const picks = await getAgentPicks(ag.persona ?? "a disciplined stock trader", withEntry);
        const rows = picks.map((p) => ({ agent_id: ag.id, trade_date: today, ticker: p.ticker, direction: p.direction }));
        if (rows.length) await supabase.from("game_agent_pick").insert(rows);
      }
    }

    return new Response(JSON.stringify({ success: true, trade_date: today, tickers, priced: withEntry.length, rival: rival?.agent_id ?? null }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-generate-pool error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
