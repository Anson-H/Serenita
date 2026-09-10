/* Runs before the app and its styles so the first paint uses the saved theme. */
(() => {
  const key = "serenita.appearance";
  const modes = ["system", "light", "dark"];
  const styles = ["apricot", "sage", "blue", "mauve", "oat"];
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const listeners = new Set();

  function read() {
    try {
      const value = JSON.parse(window.localStorage.getItem(key));
      return {
        mode: modes.includes(value?.mode) ? value.mode : "system",
        style: styles.includes(value?.style) ? value.style : "apricot"
      };
    } catch {
      return { mode: "system", style: "apricot" };
    }
  }

  let preference = read();
  let snapshot;
  function apply() {
    const theme = preference.mode === "system" ? media.matches ? "dark" : "light" : preference.mode;
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.dataset.colorStyle = preference.style;
    root.style.colorScheme = theme;
    if (snapshot?.mode === preference.mode && snapshot?.style === preference.style && snapshot?.theme === theme) return;
    snapshot = Object.freeze({ ...preference, theme });
    listeners.forEach(listener => listener());
  }

  window.serenitaAppearance = Object.freeze({
    getSnapshot: () => snapshot,
    subscribe: listener => { listeners.add(listener); return () => listeners.delete(listener); },
    set: next => {
      preference = {
        mode: modes.includes(next.mode) ? next.mode : preference.mode,
        style: styles.includes(next.style) ? next.style : preference.style
      };
      try { window.localStorage.setItem(key, JSON.stringify(preference)); } catch { /* Still usable for this page. */ }
      apply();
    }
  });
  media.addEventListener("change", apply);
  window.addEventListener("storage", event => {
    if (event.key === key || event.key === null) { preference = read(); apply(); }
  });
  apply();
})();
