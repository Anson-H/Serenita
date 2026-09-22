import { navigationLabels } from "../../../components/navigationLabels";
import {
  ConversationSettingsDetail,
  ConversationSettingsList,
  conversationSettingsSections
} from "./ConversationSettingsPanel";

import { useComposerSubmitShortcut } from "../../accountPreferences/composerSubmitShortcut";
import { useContextAssemblyDisplaySettings } from "../../accountPreferences/contextAssemblyDisplay";
import { useToolExecutionDisplayTypes } from "../../accountPreferences/toolExecutionDisplay";
import { createConversationSettingsActions } from "./conversationSettingsActions";
import { SettingsSectionLayout } from "../SettingsSectionLayout";
import { useSettingsNavigation } from "../SettingsNavigationContext";
export function ConversationSettingsSection({ accountId }: { accountId: string }) {
  const { actions: { activeSection, conversationSection, detailOpen, selectConversationSection } } = useSettingsNavigation();
  const composerSubmitShortcut = useComposerSubmitShortcut(accountId);
  const contextDisplaySettings = useContextAssemblyDisplaySettings(accountId);
  const toolDisplayTypes = useToolExecutionDisplayTypes(accountId);
  const {
    updateContextDisplayType,
    updateComposerSubmitShortcut,
    updateBaseContextDisplayMode,
    updateShowContextWindowUsage,
    updateShowRelatedContent,
    updateShowTokenUsage,
    updateShowModelIdentity,
    updateToolDisplayType,
  } = createConversationSettingsActions({
    accountId,
    contextDisplaySettings,
    toolDisplayTypes,
  });

  const { baseModes: baseContextDisplayModes, visibleContextTypes: contextDisplayTypes, showContextWindowUsage, showRelatedContent, showTokenUsage, showModelIdentity } = contextDisplaySettings;
  if (activeSection !== "conversation") return null;
  const title = conversationSettingsSections.find(section => section.key === conversationSection)?.label ?? navigationLabels.conversation;
  return <SettingsSectionLayout title={title} toolbarTitle={detailOpen ? title : navigationLabels.conversation}
    secondaryList={<ConversationSettingsList activeSection={detailOpen ? conversationSection : undefined} onSelect={selectConversationSection} />}>
    <div className="settings-detail-column">
      <ConversationSettingsDetail
        activeSection={conversationSection}
        baseContextDisplayModes={baseContextDisplayModes}
        composerSubmitShortcut={composerSubmitShortcut}
        contextDisplayTypes={contextDisplayTypes}
        showContextWindowUsage={showContextWindowUsage}
        showRelatedContent={showRelatedContent}
        showTokenUsage={showTokenUsage}
        showModelIdentity={showModelIdentity}
        toolDisplayTypes={toolDisplayTypes}
        updateBaseContextDisplayMode={updateBaseContextDisplayMode}
        updateComposerSubmitShortcut={updateComposerSubmitShortcut}
        updateContextDisplayType={updateContextDisplayType}
        updateShowRelatedContent={updateShowRelatedContent}
        updateShowContextWindowUsage={updateShowContextWindowUsage}
        updateShowTokenUsage={updateShowTokenUsage}
        updateShowModelIdentity={updateShowModelIdentity}
        updateToolDisplayType={updateToolDisplayType}
      />
    </div></SettingsSectionLayout>;
}
