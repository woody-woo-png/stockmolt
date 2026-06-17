// supabase/functions/_shared/game_logic_test.ts
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  levelFromXp,
  computeReturnPct,
  isCorrect,
  resultXp,
  nextStreak,
  avg,
  XP,
} from "./game_logic.ts";

Deno.test("levelFromXp: 경계값", () => {
  assertEquals(levelFromXp(0), 1);
  assertEquals(levelFromXp(99), 1);
  assertEquals(levelFromXp(100), 2);
  assertEquals(levelFromXp(250), 3);
  assertEquals(levelFromXp(5200), 10);
  assertEquals(levelFromXp(99999), 10);
});

Deno.test("computeReturnPct: long/short 부호", () => {
  assertEquals(computeReturnPct("long", 100, 110), 10);
  assertEquals(computeReturnPct("short", 100, 110), -10);
  assertEquals(computeReturnPct("short", 100, 90), 10);
});

Deno.test("isCorrect: 양수만 정답", () => {
  assertEquals(isCorrect(0.1), true);
  assertEquals(isCorrect(0), false);
  assertEquals(isCorrect(-1), false);
});

Deno.test("avg: 평균/빈배열", () => {
  assertEquals(avg([10, -10, 4]), 4 / 3);
  assertEquals(avg([]), 0);
});

Deno.test("nextStreak: 연속/끊김", () => {
  assertEquals(nextStreak(2, true), 3);
  assertEquals(nextStreak(5, false), 1);
});

Deno.test("resultXp: 합산과 내역", () => {
  const r = resultXp({ correctCount: 2, beatAi: true, newStreak: 3 });
  assertEquals(r.total, 140);
  assertEquals(r.breakdown.length, 4);
});

Deno.test("resultXp: 무적중·패배·스트릭1", () => {
  const r = resultXp({ correctCount: 0, beatAi: false, newStreak: 1 });
  assertEquals(r.total, XP.RESULT);
  assertEquals(r.breakdown.length, 1);
});

Deno.test("resultXp: 14일 스트릭 보너스", () => {
  const r = resultXp({ correctCount: 0, beatAi: false, newStreak: 14 });
  assertEquals(r.total, 310); // RESULT 10 + STREAK_14 300
  assertEquals(r.breakdown.length, 2);
});

Deno.test("resultXp: 30일 스트릭 보너스", () => {
  const r = resultXp({ correctCount: 0, beatAi: false, newStreak: 30 });
  assertEquals(r.total, 610); // RESULT 10 + STREAK_30 600
});

Deno.test("resultXp: 100일 스트릭 보너스", () => {
  const r = resultXp({ correctCount: 0, beatAi: false, newStreak: 100 });
  assertEquals(r.total, 2010); // RESULT 10 + STREAK_100 2000
});

Deno.test("resultXp: 비마일스톤 스트릭은 보너스 없음", () => {
  const r = resultXp({ correctCount: 0, beatAi: false, newStreak: 8 });
  assertEquals(r.total, 10); // RESULT only — streak 8 is not a milestone
  assertEquals(r.breakdown.length, 1);
});
