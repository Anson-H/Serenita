export function Switch({ checked, disabled = false, label, onChange }: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <button aria-checked={checked} aria-label={label} className="toggle-switch"
      disabled={disabled} onClick={() => onChange(!checked)} role="switch" type="button">
      <span aria-hidden="true" />
    </button>
  );
}
