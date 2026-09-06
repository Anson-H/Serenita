import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent
} from "react";
import { createPortal } from "react-dom";

import {
  focusWithoutScroll,
  isImeComposing,
  syncCommittedText
} from "../utils/inputMethod";
import { CheckIcon, ChevronLeftIcon, ChevronRightIcon, XIcon } from "./icons";

type DateTimeParts = {
  day: number;
  hour: number;
  minute: number;
  month: number;
  year: number;
};

type PickerPosition = {
  left: number;
  top: number;
  visibility: "hidden" | "visible";
  width: number;
};

type DateTimeField = "day" | "hour" | "minute" | "month" | "year";
type DateTimeDrafts = Record<DateTimeField, string>;
type DateTimePickerMode = "date" | "date-time";
type DateTimeCommitReason = "done" | "outside";

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];
const DATE_FIELDS: DateTimeField[] = ["year", "month", "day"];
const DATE_TIME_FIELDS: DateTimeField[] = ["year", "month", "day", "hour", "minute"];
const FIELD_LABELS: Record<DateTimeField, string> = {
  year: "年份",
  month: "月份",
  day: "日期",
  hour: "小时",
  minute: "分钟"
};
const FULL_DATE_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric"
});

function pad(value: number) {
  return String(value).padStart(2, "0");
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function daysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate();
}

function normalizedParts(parts: DateTimeParts): DateTimeParts {
  const year = clamp(parts.year, 1900, 2200);
  const month = clamp(parts.month, 0, 11);
  return {
    year,
    month,
    day: clamp(parts.day, 1, daysInMonth(year, month)),
    hour: clamp(parts.hour, 0, 23),
    minute: clamp(parts.minute, 0, 59)
  };
}

function partsFromValue(value: string): DateTimeParts {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
  if (match) {
    return normalizedParts({
      year: Number(match[1]),
      month: Number(match[2]) - 1,
      day: Number(match[3]),
      hour: match[4] ? Number(match[4]) : 0,
      minute: match[5] ? Number(match[5]) : 0
    });
  }
  const now = new Date();
  return {
    year: now.getFullYear(),
    month: now.getMonth(),
    day: now.getDate(),
    hour: now.getHours(),
    minute: now.getMinutes()
  };
}

function valueFromParts(parts: DateTimeParts, mode: DateTimePickerMode) {
  const normalized = normalizedParts(parts);
  const date = `${normalized.year}-${pad(normalized.month + 1)}-${pad(normalized.day)}`;
  return mode === "date" ? date : `${date}T${pad(normalized.hour)}:${pad(normalized.minute)}`;
}

function draftsFromParts(parts: DateTimeParts): DateTimeDrafts {
  return {
    year: String(parts.year),
    month: pad(parts.month + 1),
    day: pad(parts.day),
    hour: pad(parts.hour),
    minute: pad(parts.minute)
  };
}

function dateFromParts(parts: Pick<DateTimeParts, "day" | "month" | "year">) {
  return new Date(parts.year, parts.month, parts.day, 12);
}

function sameDay(left: Date, right: Date) {
  return left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate();
}

function calendarDays(year: number, month: number) {
  const firstWeekday = (new Date(year, month, 1).getDay() + 6) % 7;
  return Array.from({ length: 42 }, (_, index) => new Date(year, month, index - firstWeekday + 1, 12));
}

function displayValue(value: string, mode: DateTimePickerMode) {
  const parts = partsFromValue(value);
  const date = FULL_DATE_FORMATTER.format(dateFromParts(parts));
  return mode === "date" ? date : `${date} ${pad(parts.hour)}:${pad(parts.minute)}`;
}

export function DateTimePicker({
  ariaLabel,
  disabled,
  mode,
  onCancel,
  onChange,
  onCommit,
  value
}: {
  ariaLabel: string;
  disabled: boolean;
  mode: DateTimePickerMode;
  onCancel: () => void;
  onChange: (value: string) => void;
  onCommit: (value: string, reason: DateTimeCommitReason) => void;
  value: string;
}) {
  const dialogId = useId();
  const anchorRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const focusedFieldRef = useRef<DateTimeField | null>(null);
  const parts = partsFromValue(value);
  const [viewMonth, setViewMonth] = useState(() => new Date(parts.year, parts.month, 1, 12));
  const [fieldDrafts, setFieldDrafts] = useState<DateTimeDrafts>(() => draftsFromParts(parts));
  const [position, setPosition] = useState<PickerPosition>({ left: 15, top: 15, visibility: "hidden", width: 340 });
  const days = useMemo(
    () => calendarDays(viewMonth.getFullYear(), viewMonth.getMonth()),
    [viewMonth]
  );
  const selectedDate = dateFromParts(parts);
  const today = new Date();
  const activeFields = mode === "date" ? DATE_FIELDS : DATE_TIME_FIELDS;

  useEffect(() => {
    const nextDrafts = draftsFromParts(partsFromValue(value));
    const focusedField = focusedFieldRef.current;
    setFieldDrafts((current) => focusedField
      ? { ...nextDrafts, [focusedField]: current[focusedField] }
      : nextDrafts);
  }, [value]);

  function updateParts(nextParts: Partial<DateTimeParts>) {
    onChange(valueFromParts({ ...parts, ...nextParts }, mode));
  }

  function selectDate(date: Date, focusSelectedDay = false) {
    updateParts({ year: date.getFullYear(), month: date.getMonth(), day: date.getDate() });
    setViewMonth(new Date(date.getFullYear(), date.getMonth(), 1, 12));
    if (focusSelectedDay) {
      window.requestAnimationFrame(() => {
        focusWithoutScroll(panelRef.current?.querySelector<HTMLButtonElement>('[aria-selected="true"]') ?? null);
      });
    }
  }

  function changeMonth(offset: number) {
    const target = new Date(parts.year, parts.month + offset, 1, 12);
    const year = target.getFullYear();
    const month = target.getMonth();
    updateParts({ year, month, day: clamp(parts.day, 1, daysInMonth(year, month)) });
    setViewMonth(target);
  }

  function applyField(field: DateTimeField, nextValue: number) {
    if (field === "year" || field === "month") {
      const year = field === "year" ? nextValue : parts.year;
      const month = field === "month" ? nextValue - 1 : parts.month;
      updateParts({ year, month, day: clamp(parts.day, 1, daysInMonth(year, month)) });
      setViewMonth(new Date(year, month, 1, 12));
      return;
    }
    updateParts({ [field]: nextValue });
  }

  function fieldMaximum(field: DateTimeField) {
    if (field === "year") return 2200;
    if (field === "month") return 12;
    if (field === "day") return daysInMonth(parts.year, parts.month);
    if (field === "hour") return 23;
    return 59;
  }

  function fieldMinimum(field: DateTimeField) {
    return field === "year" ? 1900 : field === "month" || field === "day" ? 1 : 0;
  }

  function isFieldInvalid(field: DateTimeField, rawValue: string) {
    if (!rawValue || field === "year" && rawValue.length < 4) return true;
    const numericValue = Number(rawValue);
    const minimum = fieldMinimum(field);
    const maximum = fieldMaximum(field);
    return numericValue < minimum || numericValue > maximum;
  }

  function updateFieldDraft(field: DateTimeField, rawValue: string) {
    const maximumLength = field === "year" ? 4 : 2;
    const nextDraft = rawValue.replace(/\D/g, "").slice(0, maximumLength);
    setFieldDrafts((current) => ({ ...current, [field]: nextDraft }));
    if (isFieldInvalid(field, nextDraft)) return;
    const numericValue = Number(nextDraft);
    applyField(field, numericValue);
  }

  function commitField(field: DateTimeField) {
    focusedFieldRef.current = null;
    const rawValue = fieldDrafts[field];
    if (isFieldInvalid(field, rawValue)) return;
    const nextValue = Number(rawValue);
    applyField(field, nextValue);
    setFieldDrafts((current) => ({
      ...current,
      [field]: field === "year" ? String(nextValue) : pad(nextValue)
    }));
  }

  function numberInput(field: DateTimeField, label: string, maxLength: number) {
    const invalid = isFieldInvalid(field, fieldDrafts[field]);
    return (
      <input
        aria-invalid={invalid ? "true" : undefined}
        aria-label={label}
        inputMode="numeric"
        maxLength={maxLength}
        onBlur={() => commitField(field)}
        onChange={(event) => updateFieldDraft(field, event.target.value)}
        onCompositionEnd={(event) => syncCommittedText(event, (value) => updateFieldDraft(field, value))}
        onFocus={(event) => {
          focusedFieldRef.current = field;
          event.currentTarget.select();
        }}
        onKeyDown={(event) => {
          if (isImeComposing(event)) return;
          if (event.key === "Enter") {
            event.preventDefault();
            event.currentTarget.blur();
          }
        }}
        value={fieldDrafts[field]}
      />
    );
  }

  const invalidFields = activeFields.filter((field) => isFieldInvalid(field, fieldDrafts[field]));
  const hasValidationErrors = invalidFields.length > 0;

  function moveSelectedDate(event: KeyboardEvent<HTMLButtonElement>) {
    const offsets: Record<string, number> = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -7,
      ArrowDown: 7
    };
    if (event.key in offsets) {
      event.preventDefault();
      const nextDate = new Date(selectedDate);
      nextDate.setDate(nextDate.getDate() + offsets[event.key]);
      selectDate(nextDate, true);
      return;
    }
    if (event.key === "PageUp" || event.key === "PageDown") {
      event.preventDefault();
      const nextDate = new Date(selectedDate);
      nextDate.setMonth(nextDate.getMonth() + (event.key === "PageUp" ? -1 : 1));
      selectDate(nextDate, true);
    }
  }

  useLayoutEffect(() => {
    function updatePosition() {
      const anchor = anchorRef.current;
      const panel = panelRef.current;
      if (!anchor || !panel) return;
      const anchorRect = anchor.getBoundingClientRect();
      const viewportPadding = 15;
      const width = Math.min(340, window.innerWidth - viewportPadding * 2);
      const panelHeight = Math.min(panel.offsetHeight, window.innerHeight - viewportPadding * 2);
      const left = clamp(anchorRect.left, viewportPadding, window.innerWidth - width - viewportPadding);
      const spaceBelow = window.innerHeight - anchorRect.bottom - viewportPadding;
      const top = spaceBelow >= panelHeight + 8
        ? anchorRect.bottom + 8
        : Math.max(viewportPadding, anchorRect.top - panelHeight - 8);
      setPosition({ left, top, visibility: "visible", width });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    const frame = window.requestAnimationFrame(() => {
      focusWithoutScroll(panelRef.current?.querySelector<HTMLInputElement>('[aria-label="年份"]') ?? null);
    });
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, []);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || anchorRef.current?.contains(target)) return;
      if (hasValidationErrors) {
        event.preventDefault();
        const firstInvalidField = invalidFields[0];
        if (firstInvalidField) {
          window.requestAnimationFrame(() => {
            focusWithoutScroll(
              panelRef.current
                ?.querySelector<HTMLInputElement>(`[aria-label="${FIELD_LABELS[firstInvalidField]}"]`) ?? null
            );
          });
        }
        return;
      }
      onCommit(value, "outside");
    }

    function handleEscape(event: globalThis.KeyboardEvent) {
      if (isImeComposing(event)) return;
      if (event.key !== "Escape") return;
      event.preventDefault();
      onCancel();
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [fieldDrafts, onCancel, onCommit, value]);

  const panel = (
    <div
      aria-label={`${ariaLabel}选择器`}
      className="report-date-time-popover scroll-content"
      data-modal-focus-scope="true"
      data-mode={mode}
      id={dialogId}
      ref={panelRef}
      role="dialog"
      style={position}
    >
      <header className="report-date-time-header">
        <button aria-label="上个月" className="control control--titlebar control--icon control--ghost" onClick={() => changeMonth(-1)} type="button">
          <ChevronLeftIcon className="report-date-time-chevron" />
        </button>
        <strong aria-live="polite">{viewMonth.getFullYear()}年{viewMonth.getMonth() + 1}月</strong>
        <button aria-label="下个月" className="control control--titlebar control--icon control--ghost" onClick={() => changeMonth(1)} type="button">
          <ChevronRightIcon className="report-date-time-chevron" />
        </button>
      </header>
      <div aria-label="输入日期" className="report-date-time-date-fields" role="group">
        {numberInput("year", "年份", 4)}
        {numberInput("month", "月份", 2)}
        {numberInput("day", "日期", 2)}
      </div>
      <div aria-hidden="true" className="report-date-time-weekdays">
        {WEEKDAYS.map((weekday) => <span key={weekday}>{weekday}</span>)}
      </div>
      <div aria-label="日期" className="report-date-time-calendar" role="grid">
        {days.map((day) => {
          const selected = sameDay(day, selectedDate);
          const currentMonth = day.getMonth() === viewMonth.getMonth();
          const isToday = sameDay(day, today);
          return (
            <button
              aria-current={isToday ? "date" : undefined}
              aria-label={FULL_DATE_FORMATTER.format(day)}
              aria-selected={selected}
              className="report-date-time-day control control--ghost"
              data-outside-month={currentMonth ? undefined : "true"}
              key={`${day.getFullYear()}-${day.getMonth()}-${day.getDate()}`}
              onClick={() => selectDate(day)}
              onKeyDown={moveSelectedDate}
              role="gridcell"
              type="button"
            >
              {day.getDate()}
            </button>
          );
        })}
      </div>
      {mode === "date-time" ? <section aria-label="时间" className="report-date-time-time">
        <div className="report-date-time-time-fields">
          {numberInput("hour", "小时", 2)}
          <span aria-hidden="true">:</span>
          {numberInput("minute", "分钟", 2)}
        </div>
      </section> : null}
      <footer>
        <button
          className="report-date-time-now control control--ghost"
          onClick={() => {
            const now = new Date();
            onChange(valueFromParts({
              year: now.getFullYear(),
              month: now.getMonth(),
              day: now.getDate(),
              hour: now.getHours(),
              minute: now.getMinutes()
            }, mode));
            setViewMonth(new Date(now.getFullYear(), now.getMonth(), 1, 12));
          }}
          type="button"
        >
          {mode === "date" ? "今天" : "现在"}
        </button>
        <span>
          <button className="control" onClick={onCancel} type="button"><XIcon />取消</button>
          <button className="control control--primary" disabled={disabled || hasValidationErrors} onClick={() => onCommit(value, "done")} type="button">
            <CheckIcon />{disabled ? "保存中..." : "完成"}
          </button>
        </span>
      </footer>
    </div>
  );

  return (
    <span className="report-inline-edit report-date-time-editor">
      <button
        aria-label={ariaLabel}
        aria-controls={dialogId}
        aria-expanded="true"
        aria-haspopup="dialog"
        className="report-date-time-anchor"
        data-interaction-owner="row"
        ref={anchorRef}
        type="button"
      >
        {displayValue(value, mode)}
      </button>
      {createPortal(panel, document.body)}
    </span>
  );
}
