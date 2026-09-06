import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import "./styles.css";
import { installInteractionFocus } from "./utils/interactionFocus";

const disposeInteractionFocus = installInteractionFocus();
if (import.meta.hot) import.meta.hot.dispose(disposeInteractionFocus);

createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </React.StrictMode>
);
