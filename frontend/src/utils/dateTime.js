const KOLKATA_TIME_ZONE = "Asia/Kolkata";

function parseTimestamp(value, assumedOffset) {
  if (!value) return null;
  const text = String(value);
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(text);
  const date = new Date(hasZone ? text : `${text}${assumedOffset}`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function format(value, assumedOffset) {
  const date = parseTimestamp(value, assumedOffset);
  return date ? new Intl.DateTimeFormat("en-IN", {
    timeZone: KOLKATA_TIME_ZONE,
    month: "2-digit",
    day: "2-digit",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(date) : "—";
}

// SQL Server and the backend store audit/execution timestamps as timezone-naive
// Asia/Kolkata wall-clock values. Attach the intended offset without shifting them.
export function formatUtcInKolkata(value) { return format(value, "+05:30"); }

// Schedules are stored as Asia/Kolkata wall-clock values for APScheduler.
export function formatKolkata(value) { return format(value, "+05:30"); }
