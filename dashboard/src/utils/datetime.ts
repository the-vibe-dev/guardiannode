// Timestamp formatting helpers.
//
// The backend stores timestamps as UTC. SQLAlchemy's DateTime(timezone=True)
// on SQLite, however, returns naive datetimes on read — so the ISO string we
// emit can lack a trailing "Z" / "+00:00" offset. Plain `new Date(s)` then
// interprets the string as local time and the dashboard displays a wrong wall
// clock for the parent.
//
// `formatDateTime` normalizes the input: if no timezone marker is present,
// it appends "Z" before parsing. That way the value renders in the parent's
// browser-local timezone regardless of which API path produced it.

const TZ_MARKER = /(Z|[+-]\d{2}:?\d{2})$/;

function toUtcDate(input: string): Date {
  // If there's already a tz marker, parse as-is.
  if (TZ_MARKER.test(input)) {
    return new Date(input);
  }
  // Common SQLite shape: "2026-05-28 14:32:01.123456" — replace space with T
  // so JS will parse it, then mark UTC.
  const iso = input.includes("T") ? input : input.replace(" ", "T");
  return new Date(iso + "Z");
}

export function formatDateTime(input: string | number | Date | null | undefined): string {
  if (input === null || input === undefined || input === "") return "—";
  try {
    const d = typeof input === "string" ? toUtcDate(input) : new Date(input);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString();
  } catch {
    return "—";
  }
}

export function formatDate(input: string | number | Date | null | undefined): string {
  if (input === null || input === undefined || input === "") return "—";
  try {
    const d = typeof input === "string" ? toUtcDate(input) : new Date(input);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleDateString();
  } catch {
    return "—";
  }
}
