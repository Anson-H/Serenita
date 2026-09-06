import { useId, useLayoutEffect, useRef, useState, type CSSProperties, type RefObject } from "react";

import type { AddedModel } from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import {
  BrainIcon,
  ChevronLeftIcon,
  ChevronRightIcon
} from "../../components/icons";
import { focusWithModality, type FocusModality } from "../../utils/interactionFocus";

type ComposerModelControlProps = {
  controlRef: RefObject<HTMLDivElement | null>;
  currentModelName: string;
  currentThinkingLabel: string;
  modelPickerOpen: boolean;
  models: AddedModel[];
  onChooseModel: (modelId: string) => void;
  onChooseThinkingMode: (mode: string) => void;
  onSetModelPickerOpen: (open: boolean | ((open: boolean) => boolean)) => void;
  selectedModel: AddedModel | undefined;
  selectedThinkingModes: string[];
  thinkingMode: string;
  thinkingModeLabel: (mode: string) => string;
};

type ComposerPickerSection = "model";

export function ComposerModelControl({
  controlRef,
  currentModelName,
  currentThinkingLabel,
  modelPickerOpen,
  models,
  onChooseModel,
  onChooseThinkingMode,
  onSetModelPickerOpen,
  selectedModel,
  selectedThinkingModes,
  thinkingMode,
  thinkingModeLabel
}: ComposerModelControlProps) {
  const [activeSection, setActiveSection] = useState<ComposerPickerSection | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const flyoutRef = useRef<HTMLElement>(null);
  const pickerId = useId();
  const modes = selectedThinkingModes.length ? selectedThinkingModes : ["default"];
  const modeIndex = Math.max(0, modes.indexOf(thinkingMode));
  const progress = modes.length > 1 ? modeIndex / (modes.length - 1) * 100 : 0;
  const triggerLabel = `模型与推理强度：${currentModelName}，${currentThinkingLabel}`;
  function returnFocus(modality: FocusModality) {
    focusWithModality(controlRef.current?.querySelector<HTMLButtonElement>(".composer-model-trigger") ?? null, modality);
  }

  useLayoutEffect(() => {
    if (!modelPickerOpen) return;
    const updatePosition = () => {
      const popover = popoverRef.current, flyout = flyoutRef.current;
      if (!popover) return;
      const viewport = window.visualViewport;
      const style = window.getComputedStyle(popover);
      const inset = Number.parseFloat(style.getPropertyValue("--space-content")) || 15;
      const gap = Number.parseFloat(style.getPropertyValue("--space-related")) || 5;
      const left = (viewport?.offsetLeft ?? 0) + inset;
      const right = (viewport?.offsetLeft ?? 0) + (viewport?.width ?? window.innerWidth) - inset;
      const top = (viewport?.offsetTop ?? 0) + inset;
      const bottom = (viewport?.offsetTop ?? 0) + (viewport?.height ?? window.innerHeight) - inset;
      const maxWidth = Math.max(0, right - left);
      const fitHorizontally = (element: HTMLElement) => {
        element.style.translate = "none";
        const bounds = element.getBoundingClientRect();
        const shift = Math.max(left - bounds.left, Math.min(0, right - bounds.right));
        element.style.translate = `${shift}px`;
        return element.getBoundingClientRect();
      };
      popover.style.maxWidth = `${maxWidth}px`;
      const bounds = fitHorizontally(popover);
      if (!flyout) return;
      flyout.style.maxWidth = `${maxWidth}px`;
      flyout.style.translate = "none";
      if (window.getComputedStyle(flyout).position === "static") {
        flyout.removeAttribute("data-placement");
        flyout.style.maxHeight = `${Math.max(0, Math.min(380, bounds.bottom - top))}px`;
        return;
      }
      const width = flyout.getBoundingClientRect().width;
      // Keep both menus reachable when their content no longer fits side by side.
      const placement = width + gap <= bounds.left - left ? "left"
        : width + gap <= right - bounds.right ? "right"
          : bounds.top - top >= bottom - bounds.bottom ? "above" : "below";
      flyout.dataset.placement = placement;
      const flyoutBounds = fitHorizontally(flyout);
      const availableHeight = placement === "below" ? bottom - flyoutBounds.top : flyoutBounds.bottom - top;
      flyout.style.maxHeight = `${Math.max(0, Math.min(380, availableHeight))}px`;
    };
    updatePosition();
    const observer = new ResizeObserver(updatePosition);
    if (popoverRef.current) observer.observe(popoverRef.current);
    if (flyoutRef.current) observer.observe(flyoutRef.current);
    if (controlRef.current) observer.observe(controlRef.current);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    window.visualViewport?.addEventListener("resize", updatePosition);
    window.visualViewport?.addEventListener("scroll", updatePosition);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      window.visualViewport?.removeEventListener("resize", updatePosition);
      window.visualViewport?.removeEventListener("scroll", updatePosition);
    };
  }, [activeSection, controlRef, modelPickerOpen]);

  return (
    <div className="composer-model-control" ref={controlRef}>
      <button
        aria-controls={pickerId}
        aria-expanded={modelPickerOpen}
        aria-haspopup="dialog"
        aria-label={triggerLabel}
        className="control control--inline control--icon control--ghost composer-model-trigger"
        onClick={() => {
          if (!modelPickerOpen) setActiveSection(null);
          onSetModelPickerOpen(!modelPickerOpen);
        }}
        title={triggerLabel}
        type="button"
      >
        <BrainIcon className="composer-model-trigger-icon" />
      </button>

      {modelPickerOpen ? (
        <div
          aria-label="模型和推理强度"
          className={activeSection
            ? "composer-model-popover submenu-open"
            : "composer-model-popover"}
          id={pickerId}
          ref={popoverRef}
          role="dialog"
        >
          <GroupedList className="composer-model-popover-main" density="standard">
            <button
              aria-expanded={activeSection === "model"}
              aria-label={`选择模型：${currentModelName}`}
              aria-haspopup="true"
              className="composer-model-name-button"
              onClick={() => setActiveSection(activeSection ? null : "model")}
              type="button"
            >
              <span>{currentModelName}</span>
              <ChevronRightIcon className="composer-model-row-chevron" />
            </button>
            <div className="composer-reasoning-control field-row">
              <output className="composer-reasoning-value" aria-live="polite">{currentThinkingLabel}</output>
              <div className="discrete-slider" style={{ "--slider-progress": `${progress}%` } as CSSProperties}>
                <div aria-hidden="true" className="discrete-slider-ticks">
                  {modes.map(mode => <span key={mode} />)}
                </div>
                <input
                  data-interaction-owner="row"
                  aria-label="推理强度"
                  aria-valuetext={thinkingModeLabel(modes[modeIndex])}
                  disabled={modes.length < 2}
                  min={0}
                  max={Math.max(1, modes.length - 1)}
                  step={1}
                  type="range"
                  value={modeIndex}
                  onChange={event => onChooseThinkingMode(modes[Number(event.currentTarget.value)])}
                />
              </div>
            </div>
          </GroupedList>

          {activeSection ? (
            <section
              aria-label="选择模型"
              className="composer-model-flyout composer-model-submenu"
              ref={flyoutRef}
            >
              <button
                aria-label="返回模型和推理强度设置"
                className="composer-model-submenu-back"
                onClick={() => setActiveSection(null)}
                type="button"
              >
                <ChevronLeftIcon className="composer-model-row-chevron" />
              </button>
              <GroupedList
                aria-label="模型"
                className="composer-model-side-panel"
                role="radiogroup"
                density="standard"
              >
                {models.length ? (
                  models.map((model) => (
                    <button
                      aria-checked={model.model_id === selectedModel?.model_id}
                      className={
                        model.model_id === selectedModel?.model_id
                          ? "composer-model-option active"
                          : "composer-model-option"
                      }
                      key={model.model_id}
                      onClick={event => {
                        onChooseModel(model.model_id);
                        returnFocus(event.detail === 0 ? "keyboard" : "pointer");
                      }}
                      role="radio"
                      type="button"
                    >
                      <span>{model.model_name}</span>
                    </button>
                  ))
                ) : (
                  <div className="composer-model-empty">未添加聊天模型</div>
                )}
              </GroupedList>
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
