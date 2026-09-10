import type { ReactNode } from "react";
import type { AddedModel, ModelModeCapabilityProfile } from "../../api/client";
import { AudioFormatIcon, DocumentFormatIcon, ImageFormatIcon, OtherFormatIcon, TextFormatIcon, ToolCallingIcon, VideoFormatIcon } from "../../components/icons";
import { supportedEmbeddingModalities, modalityLabels } from "../modelConfiguration/modelEligibility";

export const mimeTypeGroups: {
  defaultMimeTypes: string[];
  icon: ReactNode;
  key: string;
  label: string;
  matches: (mimeType: string) => boolean;
}[] = [
    {
      defaultMimeTypes: ["image/png"],
      icon: <ImageFormatIcon className="model-capability-option-icon" />,
      key: "image",
      label: "图片",
      matches: (mimeType) => mimeType.startsWith("image/")
    },
    {
      defaultMimeTypes: ["audio/mpeg"],
      icon: <AudioFormatIcon className="model-capability-option-icon" />,
      key: "audio",
      label: "音频",
      matches: (mimeType) => mimeType.startsWith("audio/")
    },
    {
      defaultMimeTypes: ["video/mp4"],
      icon: <VideoFormatIcon className="model-capability-option-icon" />,
      key: "video",
      label: "视频",
      matches: (mimeType) => mimeType.startsWith("video/")
    },
    {
      defaultMimeTypes: ["application/pdf"],
      icon: <DocumentFormatIcon className="model-capability-option-icon" />,
      key: "pdf",
      label: "文档",
      matches: (mimeType) => mimeType === "application/pdf"
    }
  ];

export function isStandardMimeType(mimeType: string) {
  return mimeTypeGroups.some((group) => group.matches(mimeType));
}

export function ModelCapabilitySummaryIcons({ profile, direction = "all" }: {
  profile: Pick<ModelModeCapabilityProfile, "supports_text" | "file_mime_types" | "supports_tool_calling">;
  direction?: "all" | "input" | "output";
}) {
  const mimeTypes = direction === "output" ? [] : profile.file_mime_types;
  const entries = [
    ...(direction !== "all" && profile.supports_text
      ? [{ icon: <TextFormatIcon className="model-capability-option-icon" />, key: "text", label: "文本" }]
      : []),
    ...mimeTypeGroups
      .filter((group) => mimeTypes.some(group.matches))
      .map((group) => ({ icon: group.icon, key: group.key, label: group.label })),
    ...(mimeTypes.some((mimeType) => !isStandardMimeType(mimeType))
      ? [{
        icon: <OtherFormatIcon className="model-capability-option-icon" />,
        key: "other",
        label: "其它"
      }]
      : []),
    ...(direction !== "input" && profile.supports_tool_calling
      ? [{
        icon: <ToolCallingIcon className="model-capability-option-icon" />,
        key: "tool-calling",
        label: "工具调用"
      }]
      : [])
  ];
  if (!entries.length) return null;
  return (
    <span
      aria-label={`支持：${entries.map((entry) => entry.label).join("、")}`}
      title={`支持：${entries.map((entry) => entry.label).join("、")}`}
      role="img"
      className="model-capability-summary-icons"
    >
      {entries.map((entry) => (
        <span aria-hidden="true" key={entry.key}>{entry.icon}</span>
      ))}
    </span>
  );
}

export function AddedModelCapabilityIcons({ model }: { model: AddedModel }) {
  if (model.model_type === "generation") return <ModelCapabilitySummaryIcons profile={model} />;
  if (model.model_type !== "embedding") return null;
  const modalities = supportedEmbeddingModalities(model);
  if (!modalities.length) return null;
  const icons = { text: TextFormatIcon, image: ImageFormatIcon, audio: AudioFormatIcon, video: VideoFormatIcon, document: DocumentFormatIcon };
  const description = `支持输入：${modalities.map(key => modalityLabels[key]).join("、")}`;
  return <span className="model-capability-summary-icons" role="img" aria-label={description} title={description}>
    {modalities.map(key => {
      const Icon = icons[key];
      return <span aria-hidden="true" key={key}><Icon className="model-capability-option-icon" /></span>;
    })}
  </span>;
}
