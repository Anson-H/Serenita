export * from "./types";
export { clearSessionToken, getSessionToken, saveSessionToken } from "./sessionToken";

import * as authApi from "./authApi";
import * as accountSettingsApi from "./accountSettingsApi";
import * as modelProviderApi from "./modelProviderApi";
import * as conversationApi from "./conversationApi";
import * as favoriteApi from "./favoriteApi";

export const apiClient = {
  ...authApi,
  ...accountSettingsApi,
  ...modelProviderApi,
  ...conversationApi,
  ...favoriteApi
};
