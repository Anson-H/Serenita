export type TestState = {
  status: "idle" | "saving" | "testing" | "success" | "error";
  message: string;
};

export type ProviderConnectionTestState = {
  status: "idle" | "testing" | "success" | "error";
  message: string;
};

