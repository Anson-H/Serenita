function pad(value: number, width = 2) {
  return String(value).padStart(width, "0");
}

export function formatDateOnly(value: string) {
  const match = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(value);
  return match ? `${match[1]}年${Number(match[2])}月${match[3] ? `${Number(match[3])}日` : ''}` : value;
}

export function formatLocalDate(value: string | Date, includeTime = false) {
  // Calendar dates have no timezone and must never shift to the previous day.
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return formatDateOnly(value);
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return typeof value === "string" ? value : "";
  const day = formatDateOnly(localDateTimeInputValue(date).slice(0, 10));
  return includeTime ? `${day} ${pad(date.getHours())}:${pad(date.getMinutes())}` : day;
}

export function localIsoString(date = new Date()) {
  const offsetMinutes = -date.getTimezoneOffset();
  const offsetSign = offsetMinutes >= 0 ? "+" : "-";
  const absoluteOffset = Math.abs(offsetMinutes);
  const offset = `${offsetSign}${pad(Math.floor(absoluteOffset / 60))}:${pad(absoluteOffset % 60)}`;

  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
    + `.${pad(date.getMilliseconds(), 3)}${offset}`;
}

export function localDateTimeInputValue(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
