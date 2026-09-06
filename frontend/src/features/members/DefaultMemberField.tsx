import { Switch } from "../../components/Switch";

export function DefaultMemberField({ isDefault = false, value, disabled, onChange }: {
  isDefault?: boolean;
  value: boolean;
  disabled: boolean;
  onChange: (value: boolean) => void;
}) {
  return <div className="field-row">
    <span>设为默认成员</span>
    <Switch label="设为默认成员" checked={isDefault || value} disabled={disabled || isDefault} onChange={onChange} />
  </div>;
}
