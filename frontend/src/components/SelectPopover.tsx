import {useOptionActivation} from "./useOptionActivation";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import type { SelectMenuLayout } from "../utils/popoverPosition";
import { GroupedList } from "./GroupedList";
import { ChevronDownIcon } from "./icons";
import { useSelectPopover } from "./useSelectPopover";

type SelectPopoverOption<Value extends string> = {
  label: string;
  triggerLabel?: string;
  secondaryLabel?: string;
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
  const activation = useOptionActivation(select);
  return (
    <div className={["select-popover", className].filter(Boolean).join(" ")} data-density={density}
      onBlur={picker.onBlur} ref={picker.pickerRef}>
      <button {...picker.triggerProps} aria-controls={picker.open ? picker.listboxId : undefined}
        aria-expanded={picker.open} aria-haspopup="listbox" aria-label={selectedOption?.secondaryLabel ? `${ariaLabel}：${selectedOption.label} · ${selectedOption.secondaryLabel}` : ariaLabel}
        title={selectedOption ? [selectedOption.label, selectedOption.secondaryLabel].filter(Boolean).join(" · ") : undefined}
        className="select-popover-trigger" data-interaction-owner={interactionOwner}
        disabled={disabled} ref={picker.triggerRef} type="button">
        {triggerContent ?? <span className="model-provider-label"><span>{selectedOption?.triggerLabel ?? selectedOption?.label ?? placeholder ?? value}</span>{selectedOption?.secondaryLabel ? <small>{selectedOption.secondaryLabel}</small> : null}</span>}
        <ChevronDownIcon className="select-popover-icon" />
      </button>
      {picker.open && typeof document !== "undefined" ? createPortal(
        <GroupedList density="standard" aria-label={ariaLabel + "候选项"} className="select-popover-options scroll-balanced"
          data-modal-focus-scope="true" data-placement={picker.position?.placement}
          id={picker.listboxId} onBlur={picker.onBlur} ref={picker.optionsRef} role="listbox"
          style={{ left: picker.position?.left ?? 0, top: picker.position?.top ?? 0,
            width: menuWidth === "trigger" ? picker.position?.width : undefined,
            maxWidth: picker.position?.maxWidth, maxHeight: picker.position?.maxHeight,
            visibility: picker.position ? undefined : "hidden" }}>
          {options.map(option => (
            <button aria-selected={option.value === value} className="select-popover-option"
              aria-label={[option.label, option.secondaryLabel].filter(Boolean).join(" · ")} title={[option.label, option.secondaryLabel].filter(Boolean).join(" · ")}
              key={option.value} {...activation(option.value)} onKeyDown={picker.moveOptionFocus} role="option" type="button">
              <span className="model-provider-label"><span>{option.label}</span>{option.secondaryLabel ? <small>{option.secondaryLabel}</small> : null}</span>
            </button>
          ))}
        </GroupedList>, document.body
      ) : null}
    </div>
  );
}
