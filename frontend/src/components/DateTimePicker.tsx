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
import { ContentDialog } from "./ContentDialog";
import { formatLocalDate } from "../utils/localTime";

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
};

type DateTimeField = "day" | "hour" | "minute" | "month" | "year";
type DateTimeDrafts = Record<DateTimeField, string>;
type DateTimePickerMode = "date" | "date-time" | "time";
type DateTimeCommitReason = "done" | "outside";

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];
const TIME_FIELDS: DateTimeField[] = ["hour", "minute"];
const DATE_FIELDS: DateTimeField[] = ["year", "month", "day"];
const DATE_TIME_FIELDS: DateTimeField[] = ["year", "month", "day", "hour", "minute"];
const FIELD_LABELS: Record<DateTimeField, string> = {
  year: "年份",
  month: "月份",
  day: "日期",
  hour: "小时",
  minute: "分钟"
};

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
  const clock = value.match(/^(\d{2}):(\d{2})$/);
  if (clock) return normalizedParts({ year: 2000, month: 0, day: 1, hour: Number(clock[1]), minute: Number(clock[2]) });
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
  if (mode === "time") return `${pad(normalized.hour)}:${pad(normalized.minute)}`;
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
  if (mode === "time") return `${pad(parts.hour)}:${pad(parts.minute)}`;
  const date = formatLocalDate(dateFromParts(parts));
  return mode === "date" ? date : `${date} ${pad(parts.hour)}:${pad(parts.minute)}`;
}

export function DateTimePicker({
  ariaLabel,
  disabled,
  mode,
  onCancel,
  onChange,
  onCommit,
  emptyOptionLabel,
  allowLongTerm = false,
  validationMessage,
  presentation = "popover",
  value
}: {
  ariaLabel: string;
  disabled: boolean;
  mode: DateTimePickerMode;
  onCancel: () => void;
  onChange: (value: string) => void;
  onCommit: (value: string, reason: DateTimeCommitReason) => void;
  emptyOptionLabel?: string;
  allowLongTerm?: boolean;
  validationMessage?: string;
  presentation?: "popover" | "create-dialog";
  value: string;
}) {
  const dialogId = useId();
  const anchorRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const focusedFieldRef = useRef<DateTimeField | null>(null);
  const parts = partsFromValue(value);
  const latestParts = useRef(parts);
  latestParts.current = parts;
  const [viewMonth, setViewMonth] = useState(() => new Date(parts.year, parts.month, 1, 12));
  const [fieldDrafts, setFieldDrafts] = useState<DateTimeDrafts>(() => draftsFromParts(parts));
  const [position, setPosition] = useState<PickerPosition>({ left: 15, top: 15, visibility: "hidden" });
  const days = useMemo(
    () => calendarDays(viewMonth.getFullYear(), viewMonth.getMonth()),
    [viewMonth]
  );
  const selectedDate = dateFromParts(parts);
  const today = new Date();
  const activeFields = mode === "date" ? DATE_FIELDS : mode === "time" ? TIME_FIELDS : DATE_TIME_FIELDS;

  useLayoutEffect(() => {
    const nextDrafts = draftsFromParts(partsFromValue(value));
    const focusedField = focusedFieldRef.current;
    setFieldDrafts((current) => focusedField
      ? { ...nextDrafts, [focusedField]: current[focusedField] }
      : nextDrafts);
  }, [value]);

  function updateParts(nextParts: Partial<DateTimeParts>) {
    latestParts.current = normalizedParts({ ...latestParts.current, ...nextParts });
    onChange(valueFromParts(latestParts.current, mode));
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

  function commitField(field: DateTimeField, rawValue: string) {
    focusedFieldRef.current = null;
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
        className="control control--compact"
        aria-invalid={invalid ? "true" : undefined}
        aria-label={label}
        disabled={disabled}
        inputMode="numeric"
        maxLength={maxLength}
        onBlur={(event) => commitField(field, event.currentTarget.value)}
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
    if (presentation === "create-dialog") return;
    function updatePosition() {
      const anchor = anchorRef.current;
      const panel = panelRef.current;
      if (!anchor || !panel) return;
      const anchorRect = anchor.getBoundingClientRect();
      const viewportPadding = 15;
      const width = panel.offsetWidth;
      const panelHeight = Math.min(panel.offsetHeight, window.innerHeight - viewportPadding * 2);
      const left = clamp(anchorRect.left, viewportPadding, window.innerWidth - width - viewportPadding);
      const spaceBelow = window.innerHeight - anchorRect.bottom - viewportPadding;
      const top = spaceBelow >= panelHeight + 8
        ? anchorRect.bottom + 8
        : Math.max(viewportPadding, anchorRect.top - panelHeight - 8);
      setPosition({ left, top, visibility: "visible" });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    const frame = window.requestAnimationFrame(() => {
      if (panelRef.current?.contains(document.activeElement)) return;
      focusWithoutScroll(panelRef.current?.querySelector<HTMLInputElement>(`[aria-label="${mode === 'time' ? '小时' : '年份'}"]`) ?? null);
    });
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, []);

  useEffect(() => {
    if (presentation === "create-dialog") return;
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

  const fields = <>
      {mode !== "time" ? <>
      <header className="date-time-header">
        <button aria-label="上个月" className="control control--compact control--icon control--ghost" disabled={disabled} onClick={() => changeMonth(-1)} type="button">
          <ChevronLeftIcon />
        </button>
        <strong aria-live="polite">{viewMonth.getFullYear()}年{viewMonth.getMonth() + 1}月</strong>
        <button aria-label="下个月" className="control control--compact control--icon control--ghost" disabled={disabled} onClick={() => changeMonth(1)} type="button">
          <ChevronRightIcon />
        </button>
      </header>
      <div aria-label="输入日期" className="date-time-date-fields" role="group">
        {numberInput("year", "年份", 4)}
        {numberInput("month", "月份", 2)}
        {numberInput("day", "日期", 2)}
      </div>
      <div aria-hidden="true" className="date-time-weekdays">
        {WEEKDAYS.map((weekday) => <span key={weekday}>{weekday}</span>)}
      </div>
      <div aria-label="日期" className="date-time-calendar" role="grid">
        {days.map((day) => {
          const selected = !!value && value !== "long_term" && sameDay(day, selectedDate);
          const currentMonth = day.getMonth() === viewMonth.getMonth();
          const isToday = sameDay(day, today);
          return (
            <button
              aria-current={isToday ? "date" : undefined}
              aria-label={formatLocalDate(day)}
              aria-selected={selected}
              className="date-time-day control control--compact control--ghost"
              disabled={disabled}
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
      </> : null}
      {mode !== "date" ? <section aria-label="时间" className="date-time-time">
        <div className="date-time-time-fields">
          {numberInput("hour", "小时", 2)}
          <span aria-hidden="true">:</span>
          {numberInput("minute", "分钟", 2)}
        </div>
      </section> : null}
      {validationMessage ? <p role="alert" className="error-message">{validationMessage}</p> : null}
  </>;
  const actions = <>
      <footer>
        <div className="date-time-shortcuts">
          {mode !== "time" ? <button
            className="date-time-now control control--compact control--ghost"
            disabled={disabled}
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
            今天
          </button> : null}
          {allowLongTerm ? <button className="control control--compact control--ghost" type="button" disabled={disabled} aria-pressed={value === "long_term"} onClick={() => onCommit("long_term", "done")}>长期</button> : null}
          {emptyOptionLabel ? <button className="control control--compact control--ghost" type="button" disabled={disabled} aria-pressed={!value} onClick={() => onCommit("", "done")}>{emptyOptionLabel}</button> : null}
        </div>
        <span>
          <button className="control control--compact" onClick={onCancel} type="button"><XIcon />取消</button>
          <button className="control control--compact control--primary" disabled={disabled || hasValidationErrors || (!value && !emptyOptionLabel)} onClick={() => onCommit(value, "done")} type="button">
            <CheckIcon />{disabled ? "保存中..." : "完成"}
          </button>
        </span>
      </footer>
  </>;
  if (presentation === "create-dialog") return <ContentDialog creation onBack={onCancel} title={ariaLabel} onClose={onCancel} busy={disabled} bodyClassName="date-time-dialog-fields" actions={<>
    <button className="control control--primary" disabled={disabled || hasValidationErrors || !value} onClick={() => onCommit(value, "done")} type="button"><CheckIcon/>完成</button>
  </>}>{fields}</ContentDialog>;
  const panel = <div aria-label={`${ariaLabel}选择器`} className="date-time-popover scroll-content" data-modal-focus-scope="true" data-mode={mode} id={dialogId} ref={panelRef} role="dialog" style={position}>{fields}{actions}</div>;

  return (
    <span className="report-inline-edit date-time-editor">
      <button
        aria-label={ariaLabel}
        aria-controls={dialogId}
        aria-expanded="true"
        aria-haspopup="dialog"
        className="date-time-anchor"
        data-interaction-owner="row"
        ref={anchorRef}
        type="button"
      >
        {value === "long_term" ? "长期" : !value ? emptyOptionLabel ?? "必填" : displayValue(value, mode)}
      </button>
      {createPortal(panel, document.body)}
    </span>
  );
}
