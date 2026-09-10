import type { ReactNode } from "react";
import { SettingsListForwardIcon } from "./SettingsPrimitives";

export function ModelCapabilityNavigationRow({
  accessory,
  label,
  onClick
}: {
  accessory?: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className="model-capability-navigation-row grouped-labeled-navigation-row"
      onClick={onClick}
      type="button"
    >
      <span>{label}</span>
      <span className="model-capability-navigation-trailing">
        {accessory}
      </span>
      <SettingsListForwardIcon />
    </button>
  );
}

