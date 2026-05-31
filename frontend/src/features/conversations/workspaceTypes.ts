export type WorkspaceView = "home" | "health";
export type ScenarioTab = "home" | "reports" | "lifestyle";

export type QuotedContext = {
  resource_id: string;
  quote_text: string;
  preview: string;
};

export type QuoteSelection = QuotedContext & {
  left: number;
  top: number;
};

export type ActiveStream = {
  sessionId: string;
  turnId: string;
  streamId: string;
  assistantMessageId: string;
  thinkingMessageId: string | null;
  abortController: AbortController;
};

export type CancelGenerationOptions = {
  preservePartial: boolean;
  refreshAfterCancel?: boolean;
  keepSending?: boolean;
};

export type ScenarioCopy = {
  title: string;
  eyebrow: string;
  placeholder: string;
};

export const scenarioTabs: ScenarioTab[] = ["home", "reports", "lifestyle"];

export function scenarioLabel(scenario: ScenarioTab) {
  if (scenario === "reports") {
    return "报告";
  }
  if (scenario === "lifestyle") {
    return "生活";
  }
  return "首页";
}

export const scenarioCopy: Record<ScenarioTab, ScenarioCopy> = {
  home: {
    title: "新对话",
    eyebrow: "",
    placeholder: "问问Serenita"
  },
  reports: {
    title: "报告能力正在准备中",
    eyebrow: "报告占位",
    placeholder: "v0.1.0 暂不从报告页发起真实模型请求"
  },
  lifestyle: {
    title: "生活建议先作为占位入口",
    eyebrow: "生活占位",
    placeholder: "v0.1.0 暂不从生活页发起真实模型请求"
  }
};
