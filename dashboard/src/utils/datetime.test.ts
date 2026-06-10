import { describe, it, expect } from "vitest";
import { formatDateTime, formatDate } from "./datetime";

describe("formatDateTime", () => {
  it("returns an em dash for empty/nullish input", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime(undefined)).toBe("—");
    expect(formatDateTime("")).toBe("—");
  });

  it("returns an em dash for unparseable input", () => {
    expect(formatDateTime("not a date")).toBe("—");
  });

  it("treats a naive (no-offset) timestamp as UTC", () => {
    // This is the core of the tz bug fix: a naive SQLite string and the same
    // instant with an explicit Z must format identically.
    const naive = formatDateTime("2026-05-28 14:32:01");
    const utc = formatDateTime("2026-05-28T14:32:01Z");
    expect(naive).toBe(utc);
  });

  it("respects an explicit timezone offset", () => {
    const a = formatDateTime("2026-05-28T14:32:01+00:00");
    const b = formatDateTime("2026-05-28T14:32:01Z");
    expect(a).toBe(b);
  });
});

describe("formatDate", () => {
  it("handles nullish input", () => {
    expect(formatDate(null)).toBe("—");
  });

  it("normalizes naive dates to UTC", () => {
    expect(formatDate("2026-05-28 14:32:01")).toBe(formatDate("2026-05-28T14:32:01Z"));
  });
});
