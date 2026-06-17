// supabase/functions/_shared/game_logic.ts
// 순수 계산 모듈 — I/O 없음. Edge Function들이 import.

export const LEVEL_THRESHOLDS = [0, 100, 250, 500, 850, 1300, 1900, 2700, 3800, 5200];

export function levelFromXp(xp: number): number {
  let level = 1;
  for (let i = 0; i < LEVEL_THRESHOLDS.length; i++) {
    if (xp >= LEVEL_THRESHOLDS[i]) level = i + 1;
  }
  return level;
}

export function computeReturnPct(direction: "long" | "short", entry: number, exit: number): number {
  const raw = ((exit - entry) / entry) * 100;
  return direction === "long" ? raw : -raw;
}

export function isCorrect(returnPct: number): boolean {
  return returnPct > 0;
}

export function avg(nums: number[]): number {
  if (nums.length === 0) return 0;
  return nums.reduce((s, n) => s + n, 0) / nums.length;
}

export function nextStreak(prevStreak: number, playedPrevTradeDate: boolean): number {
  return playedPrevTradeDate ? prevStreak + 1 : 1;
}

export const XP = {
  SUBMIT: 15,
  RESULT: 10,
  CORRECT_EACH: 20,
  BEAT_AI: 40,
  STREAK_3: 50,
  STREAK_7: 150,
};

export interface ResultXpInput {
  correctCount: number;
  beatAi: boolean;
  newStreak: number;
}

export function resultXp(
  { correctCount, beatAi, newStreak }: ResultXpInput,
): { total: number; breakdown: { reason: string; xp: number }[] } {
  const breakdown: { reason: string; xp: number }[] = [];
  breakdown.push({ reason: "view_result", xp: XP.RESULT });
  if (correctCount > 0) breakdown.push({ reason: "correct_bonus", xp: correctCount * XP.CORRECT_EACH });
  if (beatAi) breakdown.push({ reason: "beat_ai", xp: XP.BEAT_AI });
  if (newStreak === 3) breakdown.push({ reason: "streak_3", xp: XP.STREAK_3 });
  if (newStreak === 7) breakdown.push({ reason: "streak_7", xp: XP.STREAK_7 });
  const total = breakdown.reduce((s, b) => s + b.xp, 0);
  return { total, breakdown };
}
