import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import type { SelectMenuLayout } from "../utils/popoverPosition";
import { GroupedList } from "./GroupedList";
import { ChevronDownIcon } from "./icons";
import { useSelectPopover } from "./useSelectPopover";

type SelectPopoverOption<Value extends string> = {
  label: string;
  triggerLabel?: string;
  value: Value;
};

export type InteractionOwner = "row" | "self";

export function SelectPopover<Value extends string>({
  ariaLabel, className = "", density = "standard", disabled = false, interactionOwner, menuWidth, menuAlign,
  onChange, options, placeholder, value, triggerContent
}: SelectMenuLayout & {
  ariaLabel: string;
  className?: string;
  density?: "standard" | "compact";
  disabled?: boolean;
  interactionOwner: InteractionOwner;
  onChange: (value: Value) => void | Promise<void>;
  options: SelectPopoverOption<Value>[];
  placeholder?: string;
  value: Value;
  triggerContent?: ReactNode;
}) {
  const picker = useSelectPopover({ className, disabled, optionCount: options.length, menuWidth, menuAlign });
  const selectedOption = options.find(option => option.value === value);
  function select(optionValue: Value, modality: "keyboard" | "pointer") {
    picker.close(modality);
    void onChange(optionValue);
  }
  return (
    <div className={["select-popover", className].filter(Boolean).join(" ")} data-density={density}
      onBlur={picker.onBlur} ref={picker.pickerRef}>
      <button {...picker.triggerProps} aria-controls={picker.open ? picker.listboxId : undefined}
        aria-expanded={picker.open} aria-haspopup="listbox" aria-label={ariaLabel}
        className="select-popover-trigger" data-interaction-owner={interactionOwner}
        disabled={disabled} ref={picker.triggerRef} type="button">
        {triggerContent ?? <span>{selectedOption?.triggerLabel ?? selectedOption?.label ?? placeholder ?? value}</span>}
        <ChevronDownIcon className="select-popover-icon" />
      </button>
      {picker.open && typeof document !== "undefined" ? createPortal(
        <GroupedList density="standard" aria-label={ariaLabel + "候选项"} className="select-popover-options"
          data-modal-focus-scope="true" data-placement={picker.position?.placement}
          id={picker.listboxId} onBlur={picker.onBlur} ref={picker.optionsRef} role="listbox"
          style={{ left: picker.position?.left ?? 0, top: picker.position?.top ?? 0,
            width: menuWidth === "trigger" ? picker.position?.width : undefined,
            maxWidth: picker.position?.maxWidth, maxHeight: picker.position?.maxHeight,
            visibility: picker.position ? undefined : "hidden" }}>
          {options.map(option => (
            <button aria-selected={option.value === value} className="select-popover-option"
              key={option.value} onClick={event => { if (event.detail === 0) select(option.value, "keyboard"); }}
              onKeyDown={picker.moveOptionFocus} onPointerDown={event => {
                if (event.button !== 0) return;
                event.preventDefault();
                select(option.value, "pointer");
              }} role="option" type="button">
              <span>{option.label}</span>
            </button>
          ))}
        </GroupedList>, document.body
      ) : null}
    </div>
  );
}
