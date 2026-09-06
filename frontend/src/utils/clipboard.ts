type ClipboardEnvironment = {
  documentObject?: Document;
  navigatorObject?: Navigator;
};

function restoreSelection(documentObject: Document, ranges: Range[]) {
  const selection = documentObject.getSelection?.();
  if (!selection || !ranges.length) {
    return;
  }
  selection.removeAllRanges();
  ranges.forEach((range) => selection.addRange(range));
}

function copyWithDocumentCommand(text: string, documentObject: Document) {
  if (!documentObject.body || typeof documentObject.execCommand !== "function") {
    return false;
  }

  const activeElement = documentObject.activeElement;
  const selection = documentObject.getSelection?.();
  const ranges = selection
    ? Array.from({ length: selection.rangeCount }, (_, index) => selection.getRangeAt(index).cloneRange())
    : [];
  const textarea = documentObject.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.setAttribute("aria-hidden", "true");
  Object.assign(textarea.style, {
    height: "1px",
    left: "-9999px",
    opacity: "0",
    position: "fixed",
    top: "0",
    width: "1px"
  });
  documentObject.body.append(textarea);

  try {
    textarea.focus({ preventScroll: true });
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    return documentObject.execCommand("copy");
  } finally {
    textarea.remove();
    restoreSelection(documentObject, ranges);
    const focusTarget = activeElement as (Element & {
      focus?: (options?: FocusOptions) => void;
    }) | null;
    if (typeof focusTarget?.focus === "function") {
      focusTarget.focus({ preventScroll: true });
    }
  }
}

export async function copyTextToClipboard(
  text: string,
  environment: ClipboardEnvironment = {}
) {
  const navigatorObject = environment.navigatorObject
    ?? (typeof navigator === "undefined" ? undefined : navigator);
  const documentObject = environment.documentObject
    ?? (typeof document === "undefined" ? undefined : document);
  let clipboardError: unknown;

  if (navigatorObject?.clipboard?.writeText) {
    try {
      await navigatorObject.clipboard.writeText(text);
      return;
    } catch (error) {
      clipboardError = error;
    }
  }

  if (documentObject && copyWithDocumentCommand(text, documentObject)) {
    return;
  }

  throw clipboardError instanceof Error
    ? clipboardError
    : new Error("当前浏览器无法访问剪贴板。");
}
