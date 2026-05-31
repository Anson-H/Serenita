import type { RefObject } from "react";

import type { AddedModel } from "../../api/client";

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
  return (
    <div className="composer-model-control" ref={controlRef}>
      <button
        aria-expanded={modelPickerOpen}
        aria-haspopup="dialog"
        className="composer-model-trigger"
        onClick={() => {
          onSetModelPickerOpen((open) => !open);
        }}
        type="button"
      >
        <span className="composer-model-name">{currentModelName}</span>
        <span className="composer-thinking-chip">{currentThinkingLabel}</span>
        <span aria-hidden="true">⌄</span>
      </button>

      {modelPickerOpen ? (
        <div
          aria-label="模型和推理强度"
          className="composer-model-popover"
          role="dialog"
        >
          <div className="composer-model-popover-sections">
            <section className="composer-picker-section composer-thinking-section" aria-label="思考强度">
              <div className="composer-thinking-options">
                {selectedThinkingModes.map((mode) => (
                  <button
                    className={
                      thinkingMode === mode
                        ? "composer-thinking-option active"
                        : "composer-thinking-option"
                    }
                    key={mode}
                    onClick={() => onChooseThinkingMode(mode)}
                    type="button"
                  >
                    <span>{thinkingModeLabel(mode)}</span>
                    {thinkingMode === mode ? <span aria-hidden="true">✓</span> : null}
                  </button>
                ))}
              </div>
            </section>

            <div className="composer-picker-divider" aria-hidden="true" />

            <section className="composer-picker-section composer-model-section" aria-label="模型选择">
              <aside className="composer-model-flyout composer-model-side-panel" aria-label="模型列表">
                {models.length ? (
                  models.map((model) => (
                    <button
                      className={
                        model.model_id === selectedModel?.model_id
                          ? "composer-model-option active"
                          : "composer-model-option"
                      }
                      key={model.model_id}
                      onClick={() => onChooseModel(model.model_id)}
                      type="button"
                    >
                      <span>{model.model_name}</span>
                      {model.model_id === selectedModel?.model_id ? <span aria-hidden="true">✓</span> : null}
                    </button>
                  ))
                ) : (
                  <div className="composer-model-empty">未添加聊天模型</div>
                )}
              </aside>
            </section>
          </div>
        </div>
      ) : null}
    </div>
  );
}
