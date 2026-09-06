import { createPortal } from "react-dom";
import type { SelectMenuLayout } from "../utils/popoverPosition";
import { GroupedList } from "./GroupedList";
import { CheckIcon, ChevronDownIcon } from "./icons";
import type { InteractionOwner } from "./SelectPopover";
import { useSelectPopover } from "./useSelectPopover";

type MultiSelectPopoverOption<Value extends string> = { label: string; value: Value };

export function MultiSelectPopover<Value extends string>({
  allSelectedLabel, ariaLabel, className = "", disabled = false, emptySelectedLabel,
  interactionOwner, menuWidth, menuAlign, onChange, options, selectedCountLabel, values
}: SelectMenuLayout & {
  allSelectedLabel: string;
  ariaLabel: string;
  className?: string;
  disabled?: boolean;
  emptySelectedLabel: string;
  interactionOwner: InteractionOwner;
  onChange: (values: Value[]) => void | Promise<void>;
  options: MultiSelectPopoverOption<Value>[];
  selectedCountLabel: (count: number) => string;
  values: Value[];
}) {
  const picker = useSelectPopover({ className, disabled, optionCount: options.length, menuWidth, menuAlign });
  const selectedValueSet = new Set(values);
  const selectedOptions = options.filter(option => selectedValueSet.has(option.value));
  const triggerLabel = selectedOptions.length === 0 ? emptySelectedLabel
    : selectedOptions.length === options.length ? allSelectedLabel
    : selectedOptions.length === 1 ? selectedOptions[0].label : selectedCountLabel(selectedOptions.length);
  function toggle(optionValue: Value) {
    const nextValues = selectedValueSet.has(optionValue) ? values.filter(value => value !== optionValue)
      : options.filter(option => selectedValueSet.has(option.value) || option.value === optionValue).map(option => option.value);
    void onChange(nextValues);
  }
  return (
    <div className={["select-popover", "multi-select-popover", className].filter(Boolean).join(" ")}
      onBlur={picker.onBlur} ref={picker.pickerRef}>
      <button {...picker.triggerProps} aria-controls={picker.open ? picker.listboxId : undefined}
        aria-expanded={picker.open} aria-haspopup="listbox" aria-label={ariaLabel}
        className="select-popover-trigger" data-interaction-owner={interactionOwner}
        disabled={disabled} ref={picker.triggerRef} type="button">
        <span>{triggerLabel}</span><ChevronDownIcon className="select-popover-icon" />
      </button>
      {picker.open && typeof document !== "undefined" ? createPortal(
        <GroupedList density="standard" aria-label={ariaLabel + "候选项"} aria-multiselectable="true"
          className="select-popover-options multi-select-popover-options"
          data-modal-focus-scope="true" data-placement={picker.position?.placement}
          id={picker.listboxId} onBlur={picker.onBlur} ref={picker.optionsRef} role="listbox"
          style={{ left: picker.position?.left ?? 0, top: picker.position?.top ?? 0,
            width: menuWidth === "trigger" ? picker.position?.width : undefined,
            maxWidth: picker.position?.maxWidth, maxHeight: picker.position?.maxHeight,
            visibility: picker.position ? undefined : "hidden" }}>
          {options.map(option => {
            const selected = selectedValueSet.has(option.value);
            return (
              <button aria-selected={selected} className="select-popover-option multi-select-popover-option"
                key={option.value} onClick={event => { if (event.detail === 0) toggle(option.value); }}
                onKeyDown={picker.moveOptionFocus} onPointerDown={event => {
                  if (event.button !== 0) return;
                  event.preventDefault();
                  toggle(option.value);
                }} role="option" type="button">
                <span aria-hidden="true" className="selection-check-control" data-selected={selected ? "true" : undefined}>
                  {selected ? <CheckIcon className="selection-check-icon" /> : null}
                </span><span>{option.label}</span>
              </button>
            );
          })}
        </GroupedList>, document.body
      ) : null}
    </div>
  );
}
