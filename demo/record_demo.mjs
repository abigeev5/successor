// Records the demo screen recording in demo/mock-portal (SPEC 13.1) and writes what the seed needs:
//   seed/data/recording/retake.webm — the video (compressed with ffmpeg),
//   seed/data/recording.json — title, transcript segments and steps with real timecodes.
// The narration is what the expert would say; the seed stores it as the recognized transcript,
// so the demo works without a speech model (FakeASR-style).
//
// Run from the repo root: node demo/record_demo.mjs  (needs Playwright with Chromium and ffmpeg).
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(process.env.PLAYWRIGHT_DIR ?? import.meta.url);
const { chromium } = require("playwright");

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const PORTAL = `file://${ROOT}/demo/mock-portal/index.html`;
const OUT_DIR = path.join(ROOT, "seed/data/recording");
const TMP = fs.mkdtempSync("/tmp/demo-recording-");

const STEPS = [
  {
    title: "Найти студента по фамилии",
    action: "На вкладке «Поиск студента» ввести фамилию и нажать «Найти».",
    rationale: "По фамилии быстрее, чем по номеру зачётки: номер студенты обычно не помнят.",
    say: [
      "Начинаю с поиска студента.",
      "Ищу по фамилии, так быстрее, чем по номеру зачётки: номер студенты обычно не помнят.",
    ],
    run: async (page) => {
      await page.click("#q");
      await page.type("#q", "Смирнова", { delay: 180 });
      await page.waitForTimeout(800);
      await page.click("#find");
    },
  },
  {
    title: "Проверить задолженность и номер попытки",
    action: "Открыть карточку студента и посмотреть финансовую задолженность и число попыток пересдачи.",
    rationale: "Если задолженность есть или это третья попытка, направление не оформляют: третья — только комиссия.",
    say: [
      "Открываю карточку и сразу смотрю две вещи: нет ли финансовой задолженности и какая это попытка.",
      "Если третья, направление не оформляем, это уже комиссия.",
    ],
    run: async (page) => {
      await page.click("#results tr.link");
      await page.waitForTimeout(2500);
    },
  },
  {
    title: "Перейти к оформлению направления",
    action: "Нажать «Оформить направление на пересдачу» — студент подставится сам.",
    rationale: null,
    say: ["Нажимаю «Оформить направление», студент подставляется сам."],
    run: async (page) => {
      await page.click("#to-retake");
    },
  },
  {
    title: "Выбрать дисциплину из списка",
    action: "Выбрать дисциплину в списке, а не вписывать вручную.",
    rationale: "Название должно совпадать с учебным планом, иначе кафедра не примет ведомость.",
    say: [
      "Дисциплину выбираю из списка, руками не пишу.",
      "Название должно совпадать с учебным планом, иначе кафедра не примет ведомость.",
    ],
    run: async (page) => {
      await page.selectOption("#r-discipline", "Математический анализ");
    },
  },
  {
    title: "Указать преподавателя и дату пересдачи",
    action: "Вписать фамилию преподавателя и выбрать дату пересдачи.",
    rationale: "Срок действия направления — десять календарных дней, портал считает его сам.",
    say: [
      "Указываю фамилию преподавателя и дату пересдачи.",
      "Срок действия направления десять календарных дней, портал считает его сам.",
    ],
    run: async (page) => {
      await page.click("#r-teacher");
      await page.type("#r-teacher", "Петров А. В.", { delay: 160 });
      await page.fill("#r-date", "2026-10-24");
    },
  },
  {
    title: "Оформить и распечатать направление",
    action: "Нажать «Оформить», проверить номер и срок действия, нажать «Печать».",
    rationale: "Распечатанное направление выдают студенту под подпись в журнале выдачи направлений.",
    say: [
      "Нажимаю «Оформить», проверяю номер направления и срок действия.",
      "Печатаю и выдаю студенту под подпись в журнале выдачи.",
    ],
    run: async (page) => {
      await page.click("#issue");
      await page.waitForTimeout(1500);
    },
  },
];

const SPEECH_MS_PER_CHAR = 65; // ~15 characters a second: the step lasts as long as it takes to say it

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: TMP, size: { width: 1280, height: 720 } },
});
const page = await context.newPage();
const t0 = Date.now();
await page.goto(PORTAL);
await page.waitForTimeout(1500);

const steps = [];
const segments = [];
for (const step of STEPS) {
  const start = Date.now() - t0;
  const speech = step.say.join(" ").length * SPEECH_MS_PER_CHAR;
  await step.run(page);
  const spent = Date.now() - t0 - start;
  await page.waitForTimeout(Math.max(1500, speech - spent));
  const end = Date.now() - t0;
  steps.push({ title: step.title, action: step.action, rationale: step.rationale, start_ms: start, end_ms: end });
  // Sentences share the step time in proportion to their length.
  const total = step.say.join("").length;
  let at = start;
  for (const text of step.say) {
    const length = Math.round(((end - start) * text.length) / total);
    segments.push({ start_ms: at, end_ms: at + length, text });
    at += length;
  }
}
await page.waitForTimeout(1000);
const duration = Date.now() - t0;
await context.close();
await browser.close();

const raw = fs.readdirSync(TMP).find((f) => f.endsWith(".webm"));
fs.mkdirSync(OUT_DIR, { recursive: true });
const video = path.join(OUT_DIR, "retake.webm");
// Small enough for git: 960x540, 10 fps, VP9; a silent audio track so the file looks like a real capture.
execFileSync("ffmpeg", [
  "-v", "error", "-y", "-i", path.join(TMP, raw),
  "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-shortest",
  "-vf", "scale=960:540,fps=10", "-c:v", "libvpx-vp9", "-crf", "42", "-b:v", "0",
  "-c:a", "libopus", "-b:a", "16k", video,
]);
fs.rmSync(TMP, { recursive: true, force: true });

const data = {
  _comment: "Generated by demo/record_demo.mjs. Transcript = the expert's narration; steps = what the model would return.",
  title: "Оформление направления на пересдачу",
  process: "retakes",
  duration_ms: duration,
  segments,
  steps,
};
fs.writeFileSync(path.join(ROOT, "seed/data/recording.json"), JSON.stringify(data, null, 2) + "\n");
console.log(`video ${(fs.statSync(video).size / 1024).toFixed(0)} KB, ${steps.length} steps, ${(duration / 1000).toFixed(0)} s`);
