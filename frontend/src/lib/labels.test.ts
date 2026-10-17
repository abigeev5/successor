import { describe, expect, it } from "vitest";

import { daysLeft, formatMinutes, plural } from "./labels";

describe("labels", () => {
  it("declines Russian numerals", () => {
    expect(plural(1, "день", "дня", "дней")).toBe("1 день");
    expect(plural(3, "день", "дня", "дней")).toBe("3 дня");
    expect(plural(11, "день", "дня", "дней")).toBe("11 дней");
    expect(plural(21, "день", "дня", "дней")).toBe("21 день");
    expect(plural(25, "день", "дня", "дней")).toBe("25 дней");
    expect(formatMinutes(1680)).toBe("28 минут");
  });

  it("describes the deadline", () => {
    const today = new Date(2026, 9, 17);
    expect(daysLeft("2026-10-17", today)).toBe("сегодня");
    expect(daysLeft("2026-11-07", today)).toBe("через 21 день");
    expect(daysLeft("2026-10-15", today)).toBe("просрочено на 2 дня");
    expect(daysLeft(null, today)).toBeNull();
  });
});
