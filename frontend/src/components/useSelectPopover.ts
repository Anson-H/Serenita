import { useEffect, useId, useLayoutEffect, useRef, useState,
  type KeyboardEvent, type MouseEvent, type PointerEvent as ReactPointerEvent } from "react";
import { isImeComposing } from "../utils/inputMethod";
import { focusWithModality, type FocusModality } from "../utils/interactionFocus";
import { calculatePopoverPosition, samePopoverPosition, type PopoverPosition, type SelectMenuLayout } from "../utils/popoverPosition";

/** Selection semantics stay with the caller; both pickers share their interaction surface. */
export function useSelectPopover({ className, disabled, optionCount, menuWidth, menuAlign }: SelectMenuLayout & {
  className: string;
  disabled: boolean;
  optionCount: number;
}) {
  const listboxId = useId();
  const optionsRef = useRef<HTMLDivElement | null>(null);
  const pickerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PopoverPosition | null>(null);
  const blurFrame = useRef<number | null>(null);

  function contains(node: Node | null) {
    return Boolean(node && (pickerRef.current?.contains(node) || optionsRef.current?.contains(node)));
  }

  function close(modality?: FocusModality) {
    setOpen(false);
    if (modality) {
      focusWithModality(triggerRef.current, modality);
    }
  }

  function onBlur() {
    if (blurFrame.current !== null) window.cancelAnimationFrame(blurFrame.current);
    blurFrame.current = window.requestAnimationFrame(() => {
      if (!contains(document.activeElement)) setOpen(false);
    });
  }

  useEffect(() => () => {
    if (blurFrame.current !== null) window.cancelAnimationFrame(blurFrame.current);
  }, []);

  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);

  useLayoutEffect(() => {
    if (!open) { setPosition(null); return; }
    const updatePosition = () => {
      const picker = pickerRef.current, trigger = triggerRef.current, options = optionsRef.current;
      if (!picker || !trigger || !options) return;
      const view = window.visualViewport;
      const style = window.getComputedStyle(picker);
      const dimension = (name: string, fallback: number) => {
        const value = Number.parseFloat(style.getPropertyValue(name));
        return Number.isFinite(value) ? value : fallback;
      };
      // Refresh the available width before measuring so a previously constrained menu can grow again.
      const edgeInset = dimension("--space-content", 15);
      options.style.maxWidth = `${Math.max(0, (view?.width ?? window.innerWidth) - edgeInset * 2)}px`;
      const next = calculatePopoverPosition({
        menuWidth, menuAlign,
        anchor: trigger.getBoundingClientRect(),
        viewport: { left: view?.offsetLeft ?? 0, top: view?.offsetTop ?? 0,
          width: view?.width ?? window.innerWidth, height: view?.height ?? window.innerHeight },
        edgeInset,
        gap: dimension("--space-related", 5),
        contentWidth: options.getBoundingClientRect().width,
        maxHeight: dimension("--select-popover-max-height", 320)
      });
      setPosition(current => samePopoverPosition(current, next) ? current : next);
    };
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    window.visualViewport?.addEventListener("resize", updatePosition);
    window.visualViewport?.addEventListener("scroll", updatePosition);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updatePosition);
    if (triggerRef.current) observer?.observe(triggerRef.current);
    if (optionsRef.current) observer?.observe(optionsRef.current);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      window.visualViewport?.removeEventListener("resize", updatePosition);
      window.visualViewport?.removeEventListener("scroll", updatePosition);
      observer?.disconnect();
    };
  }, [className, open, optionCount, menuWidth, menuAlign]);

  const positioned = open && position !== null;
  useLayoutEffect(() => {
    if (!positioned) return;
    const selected = optionsRef.current?.querySelector<HTMLButtonElement>('[role="option"][aria-selected="true"]');
    (selected ?? optionsRef.current?.querySelector<HTMLButtonElement>('[role="option"]'))?.focus({ preventScroll: true });
  }, [positioned]);

  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      // Selection can remove the clicked checkmark before this event reaches document.
      if (!event.composedPath().some(node => node instanceof Node && contains(node))) setOpen(false);
    }
    function escape(event: globalThis.KeyboardEvent) {
      if (event.key !== "Escape" || isImeComposing(event)) return;
      event.preventDefault();
      close("keyboard");
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  function moveOptionFocus(event: KeyboardEvent<HTMLButtonElement>) {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const options = Array.from(optionsRef.current?.querySelectorAll<HTMLButtonElement>('[role="option"]:not(:disabled)') ?? []);
    if (!options.length) return;
    event.preventDefault();
    const index = options.indexOf(event.currentTarget);
    const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1
      : event.key === "ArrowDown" ? (index + 1) % options.length : (index - 1 + options.length) % options.length;
    options[next]?.focus({ preventScroll: true });
    options[next]?.scrollIntoView({ block: "nearest" });
  }

  return {
    open, position, listboxId, optionsRef, pickerRef, triggerRef,
    close, onBlur, moveOptionFocus,
    triggerProps: {
      onClick(event: MouseEvent<HTMLButtonElement>) {
        if (event.detail === 0) { setOpen(current => !current); }
      },
      onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
        if (isImeComposing(event)) return;
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); }
      },
      onPointerDown(event: ReactPointerEvent<HTMLButtonElement>) {
        if (event.button !== 0) return;
        event.preventDefault();
        focusWithModality(triggerRef.current, "pointer");
        setOpen(current => !current);
      }
    }
  };
}
