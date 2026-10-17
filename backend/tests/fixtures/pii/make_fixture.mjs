import { createRequire } from "module";
import fs from "fs";
const require = createRequire(process.env.PLAYWRIGHT_DIR ?? import.meta.url);
const { chromium } = require("playwright");
// Regenerates student_card.png and its word boxes: node make_fixture.mjs (needs Playwright).
const OUT = new URL(".", import.meta.url).pathname;
const html = `<!doctype html><html><body style="margin:0;font:20px Arial, sans-serif;background:#fff;color:#111">
<div style="padding:24px;width:640px">
  <div class="l">Учебный портал (демо) — карточка студента</div>
  <div class="l">Студент: Смирнова Анна Павловна</div>
  <div class="l">Телефон: +7 (912) 345-67-89</div>
  <div class="l">Почта: anna.smirnova@student.demo</div>
  <div class="l">Группа: ЭК-21 Дисциплина: Математический анализ</div>
</div>
<style>.l{margin:14px 0}</style></body></html>`;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 700, height: 300 }, deviceScaleFactor: 1 });
await page.setContent(html);
const boxes = await page.evaluate(() => {
  const out = [];
  document.querySelectorAll(".l").forEach((el, line) => {
    const node = el.firstChild;
    const text = node.textContent;
    const re = /\S+/g;
    let m;
    while ((m = re.exec(text))) {
      const r = document.createRange();
      r.setStart(node, m.index);
      r.setEnd(node, m.index + m[0].length);
      const b = r.getBoundingClientRect();
      out.push({ text: m[0], x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height), line: String(line) });
    }
  });
  return out;
});
await page.screenshot({ path: `${OUT}/student_card.png` });
fs.writeFileSync(`${OUT}/student_card.ocr.json`, JSON.stringify(boxes, null, 1));
console.log(boxes.length, "boxes");
await browser.close();
