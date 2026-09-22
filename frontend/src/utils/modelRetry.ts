import type { ModelRetry } from "../api/models/modelRetryTypes";

export function modelRetryMessage(retry: ModelRetry): string {
  const attempt = `${retry.attempt}/${retry.max_attempts}`;
  switch (retry.status) {
    case "waiting":
      return `第 ${attempt} 次请求失败，等待 ${retry.delay_seconds} 秒后进行第 ${retry.attempt + 1}/${retry.max_attempts} 次尝试。`;
    case "running":
      return `正在进行第 ${attempt} 次尝试。`;
    case "completed":
      return `第 ${attempt} 次尝试已完成。`;
    case "failed":
      return `第 ${attempt} 次尝试失败，已停止重试。`;
    case "cancelled":
      return `第 ${attempt} 次尝试已取消，已停止重试。`;
  }
}
