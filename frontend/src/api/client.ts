export * from "./reportTypes";
export * from "./types";

import * as accountSettingsApi from "./accountSettingsApi";
import * as authApi from "./authApi";
import * as conversationApi from "./conversationApi";
import * as favoriteApi from "./favoriteApi";
import * as labDictionaryApi from "./labDictionaryApi";
import * as memberApi from "./memberApi";
import * as modelProviderApi from "./modelProviderApi";
import * as reportApi from "./reportApi";
import * as webAccessApi from "./webAccessApi";

export const apiClient = {
  ...authApi,
  ...memberApi,
  ...accountSettingsApi,
  ...modelProviderApi,
  ...conversationApi,
  ...favoriteApi,
  ...reportApi,
  ...labDictionaryApi,
  ...webAccessApi
};
