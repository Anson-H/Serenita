import { createElement, type ComponentPropsWithRef, type ReactNode } from "react";
import { CheckIcon } from "./icons";

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

export function GroupedCheckboxRow({label,checked,disabled=false,onChange}:{label:string;checked:boolean;disabled?:boolean;onChange:(checked:boolean)=>void}) {
  return <button className="control control--row grouped-checkbox-row" type="button" role="checkbox" aria-checked={checked} disabled={disabled} data-interaction-owner="row" onClick={()=>onChange(!checked)}>
    <span className="selection-check-control" data-selected={checked?'true':undefined} aria-hidden="true">{checked?<CheckIcon className="selection-check-icon"/>:null}</span>
    <span>{label}</span>
  </button>;
}
