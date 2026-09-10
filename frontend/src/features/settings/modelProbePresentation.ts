import {
  ModelCapabilityProbeChecks,
  ModelCapabilityProbeResponse,
  ModelCapabilityProbeStatus
} from "../../api/client";

const capabilityProbeLabels: Record<string, string> = {
  independent: "独立向量", fusion: "融合向量", batch: "批量输入",
  image: "图片", audio: "音频", video: "视频", document: "文档",
  text: "文本",
  tool_calling: "工具调用",
  image_input: "图片输入",
  pdf_input: "PDF 输入",
  audio_input: "音频输入",
  video_input: "视频输入"
};

const thinkingModeProbeLabels: Record<string, string> = {
  off: "关闭",
  minimal: "最小",
  low: "低",
  medium: "中",
  high: "高",
  xhigh: "极高",
  max: "最高"
};

function capabilityModeSummary(
  label: string,
  checks: ModelCapabilityProbeChecks
) {
  const grouped: Record<ModelCapabilityProbeStatus, string[]> = {
    supported: [],
    unsupported: [],
    unverified: [],
    not_applicable: []
  };
  Object.entries(checks).forEach(([capability, status]) => {
    grouped[status].push(capabilityProbeLabels[capability] ?? capability);
  });
  if (grouped.not_applicable.length === Object.keys(checks).length) {
    return `${label}：不适用`;
  }
  const detail = [
    grouped.supported.length ? `支持：${grouped.supported.join("、")}` : "",
    grouped.unsupported.length ? `不支持：${grouped.unsupported.join("、")}` : "",
    grouped.unverified.length ? `暂未验证：${grouped.unverified.join("、")}` : ""
  ].filter(Boolean).join("；");
  return `${label}：${detail}`;
}

export function capabilityProbeSummary(checks: ModelCapabilityProbeResponse["checks"]) {
  if (checks.embedding) return capabilityModeSummary("向量能力", checks.embedding);
  return [
    capabilityModeSummary("思考档位", Object.fromEntries(
      Object.entries(checks.thinking_modes).map(([mode, status]) => [
        thinkingModeProbeLabels[mode] ?? mode,
        status
      ])
    )),
    capabilityModeSummary("非思考", checks.non_thinking),
    capabilityModeSummary("思考", checks.thinking)
  ].join("；");
}
