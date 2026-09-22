export * from "./reports/reportTypes";
export * from "./types";

import * as accountSettingsApi from "./accounts/accountSettingsApi";
import * as authApi from "./auth/authApi";
import * as conversationApi from "./conversations/conversationApi";
import * as favoriteApi from "./favorites/favoriteApi";
import * as labDictionaryApi from "./knowledge/labDictionaryApi";
import * as memberApi from "./accounts/memberApi";
import * as modelProviderApi from "./models/modelProviderApi";
import * as reportApi from "./reports/reportApi";
import * as webAccessApi from "./web/webAccessApi";

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
