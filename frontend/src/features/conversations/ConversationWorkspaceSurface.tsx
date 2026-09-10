import { relatedResourcesForTurn } from "./relatedResources";
import { useMemo, type ReactNode } from "react";

import {
  apiClient,
  type ConversationMessage,
  type ConversationModelRecord,
  type Favorite,
  type UploadedResource
} from "../../api/client";
import { SelectPopover } from "../../components/SelectPopover";
import type { WebCitationSource } from "../../utils/markdownCitations";
import { useComposerSubmitShortcut } from "../accountPreferences/composerSubmitShortcut";
import {
  useContextAssemblyDisplaySettings,
  visibleBaseContextRecordIds
} from "../accountPreferences/contextAssemblyDisplay";
import { useToolExecutionDisplayTypes } from "../accountPreferences/toolExecutionDisplay";
import { ComposerModelControl } from "./ComposerModelControl";
import { ConversationComposer } from "./ConversationComposer";
import { ConversationMessageBubble } from "./ConversationMessageBubble";
import { ConversationTurnExecution } from "./ConversationTurnExecution";
import { HomeWorkspace } from "./HomeWorkspace";
import { QueuedInputPanel } from "./QueuedInputPanel";

import { memberDisplayName, memberLabel } from "../members/memberPresentation";
import { useMembers } from "../members/MemberProvider";
import { reportResourceStateMap } from "../reports/reportContext";
import {
  type AnnotationContextResource,
  type UploadingResource
} from "./contextResources";
import { buildConversationTurnViewModels } from "./conversationTurnViewModel";
import { contextWindowUsageFromRecords } from "./modelTokenUsage";
import type { RelatedReportReference } from "./RelatedReports";
import {
  AnnotationContextChip,
  UploadedResourceChip,
  UploadingResourceChip
} from "./ResourceChips";
import { thinkingModeLabel } from "./thinking";
import type { useConversationAttachments } from "./useConversationAttachments";
import type { useConversationLayout } from "./useConversationLayout";
import type { useConversationMessageActions } from "./useConversationMessageActions";
import type { useConversationModelControl } from "./useConversationModelControl";
import type { useConversationPageState } from "./useConversationPageState";
import type { useConversationViewState } from "./useConversationViewState";
import type { useConversationWorkspace } from "./useConversationWorkspace";

type ConversationWorkspaceSurfaceProps = {
  accountId: string;
  attachments: ReturnType<typeof useConversationAttachments>;
  favorites: Favorite[];
  layout: ReturnType<typeof useConversationLayout>;
  messageActions: ReturnType<typeof useConversationMessageActions>;
  modelControl: ReturnType<typeof useConversationModelControl>;
  onOpenReport: (reportId: string) => void | Promise<void>;
  onToggleFavorite: (message: ConversationMessage) => void | Promise<void>;
  pageState: Pick<ReturnType<typeof useConversationPageState>,
    | "activeScenario"
    | "activeStreamTurnId"
    | "cancellingTurnId"
    | "copiedMessageId"
    | "composerModelControlRef"
    | "composerTextareaRef"
    | "composerText"
    | "conversationDetail"
    | "conversationStageRef"
    | "conversationSurfaceRef"
    | "currentSessionId"
    | "editingMessageContextResources"
    | "editingMessageId"
    | "editingMessageInputRef"
    | "editingMessageText"
    | "highlightedMessageId"
    | "messageListRef"
    | "models"
    | "annotationSelection"
    | "annotatedContexts"
    | "sending"
    | "restoringQueuedInput"
    | "setAnnotatedContexts"
    | "setAnnotationSelection"
    | "setComposerText"
    | "setEditingMessageText"
    | "uploadedResources"
    | "uploadingResources"
    | "setHighlightedMessageId"
  >;
  sidebarToggle: () => ReactNode;
  composerPlaceholder?: string;
  conversationEnabled?: boolean;
  surfaceMode?: "workspace" | "composer";
  viewState: ReturnType<typeof useConversationViewState>;
  workspaceActions: ReturnType<typeof useConversationWorkspace>;
};

export function ConversationWorkspaceSurface({
  accountId,
  attachments,
  favorites,
  layout,
  messageActions,
  modelControl,
  onOpenReport,
  onToggleFavorite,
  pageState,
  sidebarToggle,
  composerPlaceholder,
  conversationEnabled = true,
  surfaceMode = "workspace",
  viewState,
  workspaceActions
}: ConversationWorkspaceSurfaceProps) {
  const members = useMembers();
  const {
    activeScenario,
    activeStreamTurnId,
    cancellingTurnId,
    copiedMessageId,
    composerModelControlRef,
    composerTextareaRef,
    composerText,
    conversationDetail,
    conversationStageRef,
    conversationSurfaceRef,
    currentSessionId: conversationSessionId,
    editingMessageContextResources,
    editingMessageId,
    editingMessageInputRef,
    editingMessageText,
    highlightedMessageId,
    messageListRef,
    models,
    annotationSelection,
    annotatedContexts,
    sending,
    setAnnotatedContexts,
    setAnnotationSelection,
    setComposerText: onComposerTextChange,
    setEditingMessageText: onEditingMessageTextChange,
    uploadedResources,
    uploadingResources
  } = pageState;
  const {
    conversationTailButtonVisible,
    preserveConversationAnchor: onConversationDisclosureAnchor,
    registerMessageElement
  } = layout;
  const {
    addSelectedTextToConversation: onAddSelectedTextToConversation,
    cancelEditingMessage: onCancelEditingMessage,
    copyMessage: onCopyMessage,
    editUserMessage: onEditUserMessage,
    removeEditingContextResource: onRemoveEditingContextResource,
    submitEditedUserMessage: onSubmitEditedUserMessage,
    updateAnnotationSelection: onUpdateAnnotationSelection
  } = messageActions;
  const {
    chooseSessionModel,
    chooseThinkingMode,
    modelPickerOpen,
    selectedModel,
    selectedThinkingModes,
    setModelPickerOpen,
    temporaryThinkingModeActive,
    thinkingMode
  } = modelControl;
  const {
    canAttachFiles,
    messages,
    selectedModelFileMimeTypes,
    selectedScenario,
    visibleMessages,
    workspaceTitle
  } = viewState;
  const {
    handleFileUpload: onFileUpload,
    removeUploadedResource: onRemoveUploadedResource
  } = attachments;
  const messagesLength = messages.length;
  const resourceStates = conversationDetail?.resource_states ?? [];
  const resourceStateByReportId = useMemo(
    () => reportResourceStateMap(resourceStates),
    [resourceStates]
  );
  const onCancelActiveGeneration = () => {
    void workspaceActions.cancelActiveGeneration({ preservePartial: true });
  };
  const onReturnToLatest = () => {
    pageState.setHighlightedMessageId(null);
    layout.returnToLatest();
  };
  const onForkConversation = workspaceActions.forkConversation;
  const onRegenerate = workspaceActions.regenerate;
  const onSubmit = workspaceActions.sendMessage;
  const composerSubmitShortcut = useComposerSubmitShortcut(accountId);
  const contextDisplaySettings = useContextAssemblyDisplaySettings(accountId);
  const toolDisplayTypes = useToolExecutionDisplayTypes(accountId);
  const visibleContextTypes = useMemo(
    () => new Set(contextDisplaySettings.visibleContextTypes),
    [contextDisplaySettings.visibleContextTypes]
  );
  const visibleBaseContextRecordIdSet = useMemo(
    () => visibleBaseContextRecordIds(visibleMessages, contextDisplaySettings.baseModes),
    [contextDisplaySettings.baseModes, visibleMessages]
  );
  const visibleToolTypes = useMemo(() => new Set(toolDisplayTypes), [toolDisplayTypes]);
  const contextWindowUsage = useMemo(
    () => contextWindowUsageFromRecords(visibleMessages),
    [visibleMessages]
  );
  const favoriteMessageIds = useMemo(
    () => new Set(
      favorites
        .filter((favorite) => favorite.source_session_id === conversationSessionId)
        .map((favorite) => favorite.source_id)
    ),
    [conversationSessionId, favorites]
  );
  const turnViewModels = useMemo(
    () => buildConversationTurnViewModels(visibleMessages, activeStreamTurnId),
    [activeStreamTurnId, visibleMessages]
  );
  function renderComposerModelControl() {
    const currentModelName = selectedModel?.model_name ?? "未添加聊天模型";
    const currentThinkingLabel = `${thinkingModeLabel(thinkingMode)}${temporaryThinkingModeActive ? " · 本轮" : ""
      }`;

    return (
      <ComposerModelControl
        controlRef={composerModelControlRef}
        currentModelName={currentModelName}
        currentThinkingLabel={currentThinkingLabel}
        modelPickerOpen={modelPickerOpen}
        models={models}
        onChooseModel={(modelId) => void chooseSessionModel(modelId)}
        onChooseThinkingMode={chooseThinkingMode}
        onSetModelPickerOpen={setModelPickerOpen}
        selectedModel={selectedModel}
        selectedThinkingModes={selectedThinkingModes}
        thinkingMode={thinkingMode}
        thinkingModeLabel={thinkingModeLabel}
      />
    );
  }

  function renderMessageBubble(
    message: ConversationMessage,
    turnTokenUsageRecords?: ConversationModelRecord[],
    relatedReportResources?: RelatedReportReference[],
    contextInputTextByResourceId?: Record<string, string>,
    citationSources?: readonly WebCitationSource[]
  ) {
    if (shouldHideStreamingAssistantPlaceholder(message)) {
      return null;
    }

    return (
      <ConversationMessageBubble
        conversationSessionId={conversationSessionId}
        citationSources={citationSources}
        contextInputTextByResourceId={contextInputTextByResourceId}
        copied={copiedMessageId === message.message_id}
        editingMessageContextResources={editingMessageContextResources}
        editingMessageId={editingMessageId}
        editingMessageInputRef={editingMessageInputRef}
        editingMessageText={editingMessageText}
        favorited={favoriteMessageIds.has(message.message_id)}
        highlightedMessageId={highlightedMessageId}
        key={message.message_id}
        message={message}
        onCancelEditingMessage={onCancelEditingMessage}
        onCopyMessage={onCopyMessage}
        onEditUserMessage={onEditUserMessage}
        onForkConversation={onForkConversation}
        onEditingMessageTextChange={onEditingMessageTextChange}
        onOpenReport={onOpenReport}
        onRegenerate={onRegenerate}
        onRegisterMessageElement={registerMessageElement}
        onRemoveEditingContextResource={onRemoveEditingContextResource}
        onSubmitEditedUserMessage={onSubmitEditedUserMessage}
        onToggleFavorite={onToggleFavorite}
        relatedReportResources={relatedReportResources}
        relatedResources={message.role==='assistant'?relatedResourcesForTurn(conversationDetail?.records??[],message.turn_id):[]}
        resourceStates={resourceStates}
        resourceStateByReportId={resourceStateByReportId}
        sending={sending || pageState.restoringQueuedInput}
        showRelatedContent={contextDisplaySettings.showRelatedContent}
        showTokenUsage={contextDisplaySettings.showTokenUsage}
        showModelIdentity={contextDisplaySettings.showModelIdentity}
        turnTokenUsageRecords={turnTokenUsageRecords}
      />
    );
  }

  function renderConversationTurns() {
    return turnViewModels.map((turn) => {
      return (
        <section
          className="conversation-turn"
          data-active={turn.active ? "true" : undefined}
          key={turn.key}
          onKeyUp={onUpdateAnnotationSelection}
          onMouseUp={onUpdateAnnotationSelection}
        >
          {turn.userRecords.map((message) => renderMessageBubble(
            message,
            undefined,
            undefined,
            turn.contextInputTextByResourceId
          ))}
          {turn.showExecution ? (
            <ConversationTurnExecution
              active={turn.active}
              activeTurnId={turn.active ? activeStreamTurnId : null}
              highlightedMessageId={highlightedMessageId}
              onRegisterMessageElement={registerMessageElement}
              showModelIdentity={contextDisplaySettings.showModelIdentity}
              records={turn.executionRecords}
              turnRecords={turn.records}
              visibleBaseContextRecordIds={visibleBaseContextRecordIdSet}
              visibleContextTypes={visibleContextTypes}
              visibleToolTypes={visibleToolTypes}
            />
          ) : null}
          {turn.assistantRecords.map((message) => renderMessageBubble(
            message,
            message.message_id === turn.usageAssistantId ? turn.modelResultRecords : undefined,
            turn.relatedReportsByAssistantId.get(message.message_id),
            undefined,
            turn.citationSourcesByAssistantId.get(message.message_id)
          ))}
        </section>
      );
    });
  }

  function shouldHideStreamingAssistantPlaceholder(message: ConversationMessage) {
    return (
      message.role === "assistant" &&
      message.status === "streaming" &&
      !message.content &&
      activeStreamTurnId === message.turn_id
    );
  }

  function renderAnnotationContextChip(annotations: AnnotationContextResource[]) {
    return (
      <AnnotationContextChip
        annotations={annotations}
        onRemove={(resourceId) => {
          setAnnotatedContexts((currentAnnotations) =>
            currentAnnotations.filter((annotation) => annotation.resource_id !== resourceId)
          );
          setAnnotationSelection(null);
        }}
        onRemoveAll={() => {
          setAnnotatedContexts([]);
          setAnnotationSelection(null);
        }}
      />
    );
  }

  function renderUploadedResourceChip(resource: UploadedResource) {
    return (
      <UploadedResourceChip
        href={
          conversationSessionId
            ? apiClient.conversationContextResourceUrl(
              conversationSessionId,
              resource.resource_id
            )
            : undefined
        }
        resource={resource}
        onRemove={onRemoveUploadedResource}
      />
    );
  }

  function renderUploadingResourceChip(resource: UploadingResource) {
    return <UploadingResourceChip key={resource.progress_key} resource={resource} />;
  }

  function renderConversationComposer() {
    return (
      <ConversationComposer
        activeStreamTurnId={activeStreamTurnId}
        canAttachFiles={surfaceMode !== "composer" && canAttachFiles && !pageState.restoringQueuedInput}
        cancellingTurnId={cancellingTurnId}
        composerRef={layout.bindComposerElement}
        composerSubmitShortcut={composerSubmitShortcut}
        composerTextareaRef={composerTextareaRef}
        composerText={composerText}
        contextWindowUsage={
          contextDisplaySettings.showContextWindowUsage ? contextWindowUsage : null
        }
        conversationEnabled={conversationEnabled}
        onCancelActiveGeneration={() => void onCancelActiveGeneration()}
        onComposerTextChange={onComposerTextChange}
        onFileUpload={onFileUpload}
        onSubmit={onSubmit}
        annotatedContexts={annotatedContexts}
        renderComposerModelControl={renderComposerModelControl}
        renderAnnotationContextChip={renderAnnotationContextChip}
        renderUploadedResourceChip={renderUploadedResourceChip}
        renderUploadingResourceChip={renderUploadingResourceChip}
        queuedInputPanel={conversationEnabled && conversationDetail?.queued_inputs.length ? (
          <QueuedInputPanel
            items={conversationDetail.queued_inputs}
            resourceUrl={(resourceId) => apiClient.conversationContextResourceUrl(
              conversationDetail.session_id, resourceId
            )}
            onDelete={workspaceActions.deleteQueuedInput}
            onEdit={workspaceActions.restoreQueuedInputToDraft}
            onReorder={workspaceActions.reorderQueuedInputs}
            onRunNow={workspaceActions.runQueuedInputNow}
          />
        ) : null}
        queuedInputCount={conversationDetail?.queued_inputs.length ?? 0}
        attachmentCapabilitiesError={viewState.attachmentCapabilitiesError}
        onRetryAttachmentCapabilities={viewState.retryAttachmentCapabilities}
        selectedModelFileMimeTypes={selectedModelFileMimeTypes}
        selectedScenarioPlaceholder={composerPlaceholder ?? selectedScenario.placeholder}
        sending={sending || pageState.restoringQueuedInput}
        uploadedResources={uploadedResources}
        uploadingResources={uploadingResources}
      />
    );
  }

  function renderMainWorkspace() {
    return (
      <HomeWorkspace
        memberControl={members.collection.members.length ? (
          <SelectPopover ariaLabel="选择成员" density="compact" interactionOwner="self"
            menuWidth="content" menuAlign="end"
            value={(conversationDetail ? conversationDetail.member_id : members.activeMemberId) ?? ""}
            triggerContent={conversationDetail ? <span>{conversationDetail.member_name ?? "未关联成员"}</span> : undefined}
            options={[{ value: "", label: "不关联成员" }, ...members.collection.members.map(member => ({
              value: member.member_id, label: memberLabel(member), triggerLabel: memberDisplayName(member)
            }))]}
            onChange={id => members.selectMember(id || null, { type: "chat" })} />
        ) : conversationSessionId ? <span className="message-meta">{conversationDetail?.member_name ?? "未关联成员"}</span> : null}
        composer={renderConversationComposer()}
        conversationStageRef={conversationStageRef}
        conversationSurfaceRef={conversationSurfaceRef}
        conversationTailButtonVisible={conversationTailButtonVisible}
        messageItems={renderConversationTurns()}
        messageListRef={messageListRef}
        messagesLength={messagesLength}
        emptyPrompt={activeScenario === "reports" ? "想先从这份医疗报告的哪一点开始？" : undefined}
        onAddSelectedTextToConversation={onAddSelectedTextToConversation}
        onConversationDisclosureAnchor={onConversationDisclosureAnchor}
        onReturnToLatest={onReturnToLatest}
        annotationSelection={annotationSelection}
        sidebarToggle={sidebarToggle()}
        workspaceTitle={workspaceTitle}
      />
    );
  }

  if (surfaceMode === "composer") {
    return (
      <div className="conversation-composer-slot">
        {renderConversationComposer()}
      </div>
    );
  }

  return renderMainWorkspace();
}
