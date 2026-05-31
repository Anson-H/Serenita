import { InputHTMLAttributes, useId, useState } from "react";

import { EyeIcon, EyeOffIcon } from "./icons";

type SecretInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  labelForAction: string;
};

export function SecretInput({ id, labelForAction, ...inputProps }: SecretInputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const [revealed, setRevealed] = useState(false);
  const toggleText = revealed ? "隐藏" : "显示";

  return (
    <span className="secret-input">
      <input {...inputProps} id={inputId} type={revealed ? "text" : "password"} />
      <button
        aria-controls={inputId}
        aria-label={`${toggleText}${labelForAction}`}
        aria-pressed={revealed}
        className="secret-toggle"
        onClick={() => setRevealed((current) => !current)}
        onMouseDown={(event) => event.preventDefault()}
        title={`${toggleText}${labelForAction}`}
        type="button"
      >
        {revealed ? <EyeOffIcon /> : <EyeIcon />}
      </button>
    </span>
  );
}
