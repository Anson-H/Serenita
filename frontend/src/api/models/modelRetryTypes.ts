export type ModelRetry = {
  attempt: number;
  max_attempts: 10;
  delay_seconds: 5 | 0;
  status: "waiting" | "running" | "completed" | "failed" | "cancelled";
};
