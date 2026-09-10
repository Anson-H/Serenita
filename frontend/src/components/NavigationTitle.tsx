import type { HTMLAttributes } from "react";

// 保留完整文本供辅助技术读取，title 提供被省略名称的悬停查看。
export function NavigationTitle({ as: Tag = "h2", title, ...props }: {
  as?: "h1" | "h2" | "strong";
  title: string;
  "data-modal-initial-focus"?: boolean;
} & Omit<HTMLAttributes<HTMLElement>, "title">) {
  return <Tag {...props} title={title}>{title}</Tag>;
}
