import {
  writeComposerSubmitShortcut,
  type ComposerSubmitShortcut
} from "../accountPreferences/composerSubmitShortcut";
import type { ContextAssemblyDisplaySettings } from "../accountPreferences/contextAssemblyDisplay";
import {
  writeContextAssemblyDisplaySettings,
  type BaseContextAssemblyDisplayMode,
  type BaseContextAssemblyType
} from "../accountPreferences/contextAssemblyDisplay";
import {
  writeToolExecutionDisplayTypes,
  type ToolExecutionDisplayType
} from "../accountPreferences/toolExecutionDisplay";

type Dependencies = {
  accountId: string;
  contextDisplaySettings: ContextAssemblyDisplaySettings;
  toolDisplayTypes: ToolExecutionDisplayType[];
};

export function createConversationSettingsActions({ accountId, contextDisplaySettings, toolDisplayTypes }: Dependencies) {
  function updateContextDisplayType(contextType: string, visible: boolean) {
    writeContextAssemblyDisplaySettings(accountId, {
      ...contextDisplaySettings,
      visibleContextTypes: visible
        ? [...new Set([...contextDisplaySettings.visibleContextTypes, contextType])]
        : contextDisplaySettings.visibleContextTypes.filter((item) => item !== contextType)
    });
  }

  function updateComposerSubmitShortcut(shortcut: ComposerSubmitShortcut) {
    writeComposerSubmitShortcut(accountId, shortcut);
  }

  function updateBaseContextDisplayMode(
    contextType: BaseContextAssemblyType,
    mode: BaseContextAssemblyDisplayMode
  ) {
    writeContextAssemblyDisplaySettings(accountId, {
      ...contextDisplaySettings,
      baseModes: {
        ...contextDisplaySettings.baseModes,
        [contextType]: mode
      }
    });
  }

  function updateShowContextWindowUsage(visible: boolean) {
    writeContextAssemblyDisplaySettings(accountId, {
      ...contextDisplaySettings,
      showContextWindowUsage: visible
    });
  }

  function updateShowRelatedContent(visible: boolean) {
    writeContextAssemblyDisplaySettings(accountId, {
      ...contextDisplaySettings,
      showRelatedContent: visible
    });
  }

  function updateShowTokenUsage(visible: boolean) {
    writeContextAssemblyDisplaySettings(accountId, {
      ...contextDisplaySettings,
      showTokenUsage: visible
    });
  }

  function updateShowModelIdentity(visible: boolean) {
    writeContextAssemblyDisplaySettings(accountId, {
      ...contextDisplaySettings,
      showModelIdentity: visible
    });
  }

  function updateToolDisplayType(type: ToolExecutionDisplayType, visible: boolean) {
    writeToolExecutionDisplayTypes(
      accountId,
      visible
        ? [...new Set([...toolDisplayTypes, type])]
        : toolDisplayTypes.filter((item) => item !== type)
    );
  }
  return {
    updateContextDisplayType,
    updateComposerSubmitShortcut,
    updateBaseContextDisplayMode,
    updateShowContextWindowUsage,
    updateShowRelatedContent,
    updateShowTokenUsage,
    updateShowModelIdentity,
    updateToolDisplayType
  };
}
