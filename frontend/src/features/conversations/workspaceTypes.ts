
export type ScenarioTab = "home" | "reports";

export type AnnotatedContext = {
  resource_id: string;
  source_record_id: string;
  annotation_text: string;
  preview: string;
};

export type AnnotationSelection = Omit<AnnotatedContext, "resource_id"> & {
  left: number;
  top: number;
};

export type ActiveStream = {
  sessionId: string;
  turnId: string;
  streamId: string;
  finalAssistantMessageId: string;
  abortController: AbortController;
};

type ScenarioCopy = {
  title: string;
  eyebrow: string;
  placeholder: string;
};

export const scenarioCopy: Record<ScenarioTab, ScenarioCopy> = {
  home: {
    title: "新聊天",
    eyebrow: "",
    placeholder: "问问Serenita"
  },
  reports: {
    title: "医疗报告问答",
    eyebrow: "医疗报告",
    placeholder: "询问这份医疗报告的异常或后续关注点"
  }
};
