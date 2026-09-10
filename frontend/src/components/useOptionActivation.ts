import { useRef, type PointerEvent, type MouseEvent } from "react";

/** Preserve desktop focus; touch selects only after a completed tap. */
export function useOptionActivation<Value extends string>(
  activate: (value: Value, modality: "keyboard" | "pointer") => void,
) {
  const touch = useRef<{
    value: Value;
    x: number;
    y: number;
    moved: boolean;
  } | null>(null);
  return (value: Value) => ({
    onPointerDown(event: PointerEvent<HTMLButtonElement>) {
      if (event.button !== 0) return;
      if (event.pointerType === "touch") {
        touch.current = {
          value,
          x: event.clientX,
          y: event.clientY,
          moved: false,
        };
      } else {
        touch.current = null;
        event.preventDefault();
        activate(value, "pointer");
      }
    },
    onPointerMove(event: PointerEvent<HTMLButtonElement>) {
      const start = touch.current;
      if (
        start &&
        Math.hypot(event.clientX - start.x, event.clientY - start.y) > 8
      )
        start.moved = true;
    },
    onPointerCancel() {
      touch.current = null;
    },
    onClick(event: MouseEvent<HTMLButtonElement>) {
      if (event.detail === 0) activate(value, "keyboard");
      else if (touch.current?.value === value && !touch.current.moved)
        activate(value, "pointer");
      touch.current = null;
    },
  });
}
