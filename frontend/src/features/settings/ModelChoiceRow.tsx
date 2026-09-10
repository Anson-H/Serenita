import type { ReactNode } from "react";
import { CheckIcon } from "../../components/icons";

export function ModelChoiceRow({
  active,
  disabled,
  formatHint,
  icon,
  label,
  onClick
}: {
  active: boolean;
  disabled: boolean;
  formatHint?: string;
  icon?: ReactNode;
  label: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      aria-pressed={active}
      className="model-capability-choice-row"
      disabled={disabled}
      onClick={onClick}
      title={formatHint}
      type="button"
    >
      <span
        aria-hidden="true"
        className="model-choice-indicator selection-check-control"
        data-selected={active ? "true" : undefined}
      >
        {active ? (
          <CheckIcon className="model-choice-check-icon selection-check-icon" />
        ) : null}
      </span>
      <span className="model-capability-choice-copy">
        {icon ? <span aria-hidden="true">{icon}</span> : null}
        <span>{label}</span>
      </span>
    </button>
  );
}

