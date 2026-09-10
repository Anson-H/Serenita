import { navigationLabels } from "../../components/navigationLabels";
import { GroupedList } from "../../components/GroupedList";
import { SelectPopover } from "../../components/SelectPopover";
import { Switch } from "../../components/Switch";
import {
  composerSubmitShortcutOptions,
  type ComposerSubmitShortcut
} from "../accountPreferences/composerSubmitShortcut";
import {
  baseContextAssemblyDisplayModeOptions,
  contextAssemblyDisplayOptions,
  isBaseContextAssemblyType,
  type BaseContextAssemblyDisplayMode,
  type BaseContextAssemblyType
} from "../accountPreferences/contextAssemblyDisplay";
import {
  toolExecutionDisplayOptions,
  type ToolExecutionDisplayType
} from "../accountPreferences/toolExecutionDisplay";
import { SettingsControlRow, SettingsListForwardIcon, SettingsListPanel } from "./SettingsPrimitives";
import type { ConversationSettingsSection } from "./settingsTypes";

export const conversationSettingsSections: readonly {
  key: ConversationSettingsSection;
  label: string;
}[] = [
    { key: "composer", label: "输入框" },
    { key: "response", label: "回答显示" }
  ];

const baseContextOptions = contextAssemblyDisplayOptions.filter((option) =>
  isBaseContextAssemblyType(option.contextType)
);
const traceOptions = contextAssemblyDisplayOptions.filter((option) => option.group === "输入追溯");

export function ConversationSettingsList({
  activeSection,
  onSelect
}: {
  activeSection?: ConversationSettingsSection;
  onSelect: (section: ConversationSettingsSection) => void;
}) {
  return (
    <SettingsListPanel
      bodyClassName="conversation-settings-list-body"
      className="conversation-settings-list"
      title={navigationLabels.conversation}
      titleId="conversation-settings-list-title"
    >
      <GroupedList
        as="nav"
        density="standard"
        aria-label="聊天设置类别"
        className="conversation-settings-sections"
      >
        {conversationSettingsSections.map((section) => {
          const active = activeSection === section.key;
          return (
            <button
              aria-current={active ? "page" : undefined}
              className={active ? "settings-subnav-item selected" : "settings-subnav-item"}
              key={section.key}
              onClick={() => onSelect(section.key)}
              type="button"
            >
              <span>
                <strong>{section.label}</strong>
              </span>
              <SettingsListForwardIcon className="settings-subnav-icon" />
            </button>
          );
        })}
      </GroupedList>
    </SettingsListPanel>
  );
}

export function ConversationSettingsDetail({
  activeSection,
  baseContextDisplayModes,
  composerSubmitShortcut,
  contextDisplayTypes,
  showContextWindowUsage,
  showRelatedContent,
  showTokenUsage,
  showModelIdentity,
  toolDisplayTypes,
  updateBaseContextDisplayMode,
  updateComposerSubmitShortcut,
  updateContextDisplayType,
  updateShowRelatedContent,
  updateShowContextWindowUsage,
  updateShowTokenUsage,
  updateShowModelIdentity,
  updateToolDisplayType
}: {
  activeSection: ConversationSettingsSection;
  baseContextDisplayModes: Record<BaseContextAssemblyType, BaseContextAssemblyDisplayMode>;
  composerSubmitShortcut: ComposerSubmitShortcut;
  contextDisplayTypes: string[];
  showContextWindowUsage: boolean;
  showRelatedContent: boolean;
  showTokenUsage: boolean;
  showModelIdentity: boolean;
  toolDisplayTypes: ToolExecutionDisplayType[];
  updateBaseContextDisplayMode: (
    contextType: BaseContextAssemblyType,
    mode: BaseContextAssemblyDisplayMode
  ) => void;
  updateComposerSubmitShortcut: (shortcut: ComposerSubmitShortcut) => void;
  updateContextDisplayType: (contextType: string, visible: boolean) => void;
  updateShowRelatedContent: (visible: boolean) => void;
  updateShowContextWindowUsage: (visible: boolean) => void;
  updateShowTokenUsage: (visible: boolean) => void;
  updateShowModelIdentity: (visible: boolean) => void;
  updateToolDisplayType: (type: ToolExecutionDisplayType, visible: boolean) => void;
}) {
  return (
    <section className="settings-section conversation-settings-detail">
      {activeSection === "composer" ? (
        <GroupedList layout="fields" className="settings-control-list conversation-settings-option-list" density="standard">
          <SettingsControlRow
            control={(
              <SelectPopover
                ariaLabel="设置发送快捷键"
                menuWidth="content" menuAlign="end" interactionOwner="row"
                onChange={updateComposerSubmitShortcut}
                options={composerSubmitShortcutOptions}
                value={composerSubmitShortcut}
              />
            )}
            label="发送快捷键"
            layout="field"
          />
          <SettingsControlRow
            control={(
              <Switch
                checked={showContextWindowUsage}
                label="显示上下文使用情况"
                onChange={updateShowContextWindowUsage}
              />
            )}
            label="显示上下文使用情况"
          />
        </GroupedList>
      ) : null}

      {activeSection === "response" ? (
        <>
          <GroupedList layout="fields" className="settings-control-list conversation-settings-option-list" density="standard">
            <SettingsControlRow
              control={(
                <Switch
                  checked={showModelIdentity}
                  label="显示模型标识"
                  onChange={updateShowModelIdentity}
                />
              )}
              label="显示模型标识"
            />
            <SettingsControlRow
              control={(
                <Switch
                  checked={showRelatedContent}
                  label="显示相关内容"
                  onChange={updateShowRelatedContent}
                />
              )}
              label="显示相关内容"
            />
            <SettingsControlRow
              control={(
                <Switch
                  checked={showTokenUsage}
                  label="显示词元用量"
                  onChange={updateShowTokenUsage}
                />
              )}
              label="显示词元用量"
            />
          </GroupedList>

          <section
            aria-labelledby="conversation-system-group-title"
            className="conversation-settings-group"
          >
            <h3 id="conversation-system-group-title">系统与能力</h3>
            <GroupedList layout="fields" className="settings-control-list conversation-settings-option-list" density="standard">
              {baseContextOptions.map((option) => {
                const contextType = option.contextType as BaseContextAssemblyType;
                return (
                  <SettingsControlRow
                    control={(
                      <SelectPopover
                        ariaLabel={`设置${option.label}的显示频率`}
                        className="context-display-picker"
                        menuWidth="content" menuAlign="end" interactionOwner="row"
                        onChange={(mode) => updateBaseContextDisplayMode(contextType, mode)}
                        options={baseContextAssemblyDisplayModeOptions}
                        value={baseContextDisplayModes[contextType]}
                      />
                    )}
                    key={contextType}
                    label={option.label}
                    layout="field"
                  />
                );
              })}
            </GroupedList>
          </section>

          <section
            aria-labelledby="conversation-tools-group-title"
            className="conversation-settings-group"
          >
            <h3 id="conversation-tools-group-title">工具记录</h3>
            <GroupedList layout="fields" className="settings-control-list conversation-settings-option-list" density="standard">
              {toolExecutionDisplayOptions.map((option) => (
                <SettingsControlRow
                  control={(
                    <Switch
                      checked={toolDisplayTypes.includes(option.type)}
                      label={`显示${option.label}`}
                      onChange={(visible) => updateToolDisplayType(option.type, visible)}
                    />
                  )}
                  key={option.type}
                  label={option.label}
                />
              ))}
            </GroupedList>
          </section>

          <section
            aria-labelledby="conversation-trace-group-title"
            className="conversation-settings-group"
          >
            <h3 id="conversation-trace-group-title">输入追溯</h3>
            <GroupedList layout="fields" className="settings-control-list conversation-settings-option-list" density="standard">
              {traceOptions.map((option) => (
                <SettingsControlRow
                  control={(
                    <Switch
                      checked={contextDisplayTypes.includes(option.contextType)}
                      label={`显示${option.label}`}
                      onChange={(visible) => updateContextDisplayType(option.contextType, visible)}
                    />
                  )}
                  key={option.contextType}
                  label={option.label}
                />
              ))}
            </GroupedList>
          </section>
        </>
      ) : null}
    </section>
  );
}
