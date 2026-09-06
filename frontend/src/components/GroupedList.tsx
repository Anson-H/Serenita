import { createElement, type ComponentPropsWithRef, type ReactNode } from "react";

type ListElement = "div" | "ul" | "ol" | "dl" | "nav";
type GroupedListProps<Element extends ListElement> = {
  as?: Element;
  layout?: "plain" | "fields" | "navigation";
  density: "standard" | "compact";
  selectionMode?: "single" | "multiple";
} & ComponentPropsWithRef<Element>;

/** Layout selects column tracks; density sizes rows and their controls together. */
export function GroupedList<Element extends ListElement = "div">({
  as,
  children,
  className = "",
  layout = "plain",
  density,
  selectionMode,
  ...props
}: GroupedListProps<Element>) {
  return createElement(as ?? "div", {
    ...props,
    className: ["grouped-object-list", className].filter(Boolean).join(" "),
    "data-layout": layout,
    "data-density": density,
    "data-selection-mode": selectionMode
  }, children);
}

export function ReadonlyField({ className = "", label, value }: {
  className?: string;
  label: ReactNode;
  value: ReactNode;
}) {
  return (
    <div className={["field-row", className].filter(Boolean).join(" ")}>
      <span className="field-label">{label}</span>
      <span className="field-value">{value}</span>
    </div>
  );
}
