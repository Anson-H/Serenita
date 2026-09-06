import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type SyntheticEvent
} from "react";

export function useDeferredDisclosureBody() {
  const [bodyMounted, setBodyMounted] = useState(false);
  const onToggle = useCallback((event: SyntheticEvent<HTMLDetailsElement>) => {
    if (event.currentTarget.open) {
      setBodyMounted(true);
    }
  }, []);
  return { bodyMounted, onToggle };
}

export function useTurnExecutionDisclosure(active: boolean, revealRequested: boolean) {
  const [open, setOpen] = useState(active);
  const [bodyMounted, setBodyMounted] = useState(active);
  const wasActiveRef = useRef(active);

  useEffect(() => {
    if (active) {
      setOpen(true);
      setBodyMounted(true);
    } else if (wasActiveRef.current) {
      setOpen(false);
    }
    wasActiveRef.current = active;
  }, [active]);

  useEffect(() => {
    if (!revealRequested) {
      return;
    }
    setOpen(true);
    setBodyMounted(true);
  }, [revealRequested]);

  const onToggle = useCallback((event: SyntheticEvent<HTMLDetailsElement>) => {
    const nextOpen = event.currentTarget.open;
    setOpen(nextOpen);
    if (nextOpen) {
      setBodyMounted(true);
    }
  }, []);

  return { bodyMounted, onToggle, open };
}
