import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const shellSource = readFileSync(join(root, "src/features/settings/SettingsShell.tsx"), "utf8");
const viewSource = readFileSync(join(root, "src/features/settings/SettingsView.tsx"), "utf8");

assert(
  !viewSource.includes("provider.configured ?"),
  "provider list status must not use saved configuration as the checkmark source"
);

assert(
  viewSource.includes("providerConnectionStates"),
  "provider list should render connection test states for each provider"
);

assert(
  viewSource.includes("测试连接：${provider.provider_name}") &&
    viewSource.includes("testProviderConnection(provider.provider_id, { notify: true })"),
  "provider list status icon should manually test that provider and notify the user"
);

assert(
  shellSource.includes("testAllProviderConnections(providerResponse.providers") &&
    shellSource.includes("status: \"idle\"") &&
    shellSource.includes("notify?: boolean"),
  "loading provider settings should reset every provider to the lightning state and auto-test connections"
);

assert(
  !shellSource.includes("window.alert(") &&
    viewSource.includes("connectionState.message || \"测试连接\"") &&
    shellSource.includes("scheduleProviderConnectionFeedbackReset"),
  "manual provider connection tests should show success or failure on the provider row icon"
);
