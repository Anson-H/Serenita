import { InputHTMLAttributes, type ReactNode, useEffect, useId, useState } from "react";

import { EyeIcon, EyeOffIcon } from "./icons";

type SecretInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  beforeToggleAction?: ReactNode;
  labelForAction: string;
  onReveal?: () => boolean | void | Promise<boolean | void>;
};

export function SecretInput({
  beforeToggleAction,
  id,
  labelForAction,
  onReveal,
  ...inputProps
}: SecretInputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const [revealed, setRevealed] = useState(false);
  const [revealing, setRevealing] = useState(false);
  const toggleText = revealed ? "隐藏" : "显示";

  useEffect(() => {
    if (!inputProps.value) setRevealed(false);
  }, [inputProps.value]);

  async function toggleSecret() {
    if (revealed) {
      setRevealed(false);
      return;
    }
    if (onReveal) {
      setRevealing(true);
      try {
        const allowed = await onReveal();
        if (allowed === false) return;
      } catch {
        return;
      } finally {
        setRevealing(false);
      }
    }
    setRevealed(true);
  }

  return (
    <span className={beforeToggleAction ? "secret-input with-before-toggle" : "secret-input"}>
      <input {...inputProps} id={inputId} type={revealed ? "text" : "password"} />
      {beforeToggleAction ? (
        <span className="secret-before-toggle">{beforeToggleAction}</span>
      ) : null}
      <button
        aria-controls={inputId}
        aria-label={`${toggleText}${labelForAction}`}
        aria-pressed={revealed}
        aria-busy={revealing}
        className="control control--inline control--icon control--ghost secret-toggle"
        data-interaction-owner="self"
        disabled={inputProps.disabled || revealing}
        onClick={() => void toggleSecret()}
        onMouseDown={(event) => event.preventDefault()}
        title={revealing ? `正在读取${labelForAction}` : `${toggleText}${labelForAction}`}
        type="button"
      >
        {revealed ? <EyeOffIcon /> : <EyeIcon />}
      </button>
    </span>
  );
}
