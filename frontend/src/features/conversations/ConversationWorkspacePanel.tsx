import type { ReactNode } from "react";

import { ConversationWorkspaceSurface } from "./ConversationWorkspaceSurface";
import type { useConversationAttachments } from "./useConversationAttachments";
import type { useConversationBranching } from "./useConversationBranching";
import type { useConversationLayout } from "./useConversationLayout";
import type { useConversationMessageActions } from "./useConversationMessageActions";
import type { useConversationModelControl } from "./useConversationModelControl";
import type { useConversationPageState } from "./useConversationPageState";
import type { useConversationViewState } from "./useConversationViewState";
import type { useConversationWorkspace } from "./useConversationWorkspace";
import type { Favorite } from "../../api/client";

type ConversationWorkspacePanelProps = {
  attachments: ReturnType<typeof useConversationAttachments>;
  branching: ReturnType<typeof useConversationBranching>;
  favorites: Favorite[];
  layout: ReturnType<typeof useConversationLayout>;
  messageActions: ReturnType<typeof useConversationMessageActions>;
  modelControl: ReturnType<typeof useConversationModelControl>;
  pageState: ReturnType<typeof useConversationPageState>;
  sidebarToggle: () => ReactNode;
  viewState: ReturnType<typeof useConversationViewState>;
  workspaceActions: ReturnType<typeof useConversationWorkspace>;
  onToggleFavorite: (message: Parameters<ReturnType<typeof useConversationMessageActions>["copyMessage"]>[0]) => void | Promise<void>;
};

export function ConversationWorkspacePanel({
  attachments,
  branching,
  favorites,
  layout,
  messageActions,
  modelControl,
  onToggleFavorite,
  pageState,
  sidebarToggle,
  viewState,
  workspaceActions
}: ConversationWorkspacePanelProps) {
  return (
    <ConversationWorkspaceSurface
      activeScenario={pageState.activeScenario}
      activeStreamTurnId={pageState.activeStreamTurnId}
      activeView={pageState.activeView}
      activelyThinkingTurnId={pageState.activelyThinkingTurnId}
      branchAfter={branching.branchAfter}
      branchParentKey={branching.branchParentKey}
      canAttachFiles={viewState.canAttachFiles}
      cancellingTurnId={pageState.cancellingTurnId}
      childrenByParent={branching.childrenByParent}
      chooseSessionModel={modelControl.chooseSessionModel}
      chooseThinkingMode={modelControl.chooseThinkingMode}
      copiedMessageId={pageState.copiedMessageId}
      composerError={pageState.composerError}
      composerModelControlRef={pageState.composerModelControlRef}
      composerRef={pageState.composerRef}
      composerTextareaRef={pageState.composerTextareaRef}
      composerText={pageState.composerText}
      conversationStageRef={pageState.conversationStageRef}
      conversationSurfaceRef={pageState.conversationSurfaceRef}
      editingMessageContextResources={pageState.editingMessageContextResources}
      editingMessageId={pageState.editingMessageId}
      editingMessageInputRef={pageState.editingMessageInputRef}
      editingMessageText={pageState.editingMessageText}
      favorites={favorites}
      highlightedMessageId={pageState.highlightedMessageId}
      messageListRef={pageState.messageListRef}
      messageRefs={pageState.messageRefs}
      messagesLength={viewState.messages.length}
      modelPickerOpen={modelControl.modelPickerOpen}
      models={pageState.models}
      onAddSelectedTextToConversation={messageActions.addSelectedTextToConversation}
      onCancelActiveGeneration={() => {
        void workspaceActions.cancelActiveGeneration({ preservePartial: true });
      }}
      onCancelEditingMessage={messageActions.cancelEditingMessage}
      onComposerTextChange={pageState.setComposerText}
      onConversationScroll={layout.updateConversationScrollState}
      onCopyMessage={messageActions.copyMessage}
      onEditUserMessage={messageActions.editUserMessage}
      onEditingMessageTextChange={pageState.setEditingMessageText}
      onFileUpload={attachments.handleFileUpload}
      onRegenerate={workspaceActions.regenerate}
      onRemoveEditingContextResource={messageActions.removeEditingContextResource}
      onRemoveUploadedResource={attachments.removeUploadedResource}
      onRestoreBranchPreview={branching.restoreBranchPreview}
      onSubmit={workspaceActions.sendMessage}
      onSubmitEditedUserMessage={messageActions.submitEditedUserMessage}
      onSwitchBranch={branching.switchBranch}
      onToggleFavorite={onToggleFavorite}
      onUpdateQuoteSelection={messageActions.updateQuoteSelection}
      parentForNextMessage={pageState.parentForNextMessage}
      quoteSelection={pageState.quoteSelection}
      quotedContext={pageState.quotedContext}
      selectedModel={modelControl.selectedModel}
      selectedModelFileMimeTypes={viewState.selectedModelFileMimeTypes}
      selectedScenario={viewState.selectedScenario}
      selectedThinkingModes={modelControl.selectedThinkingModes}
      sending={pageState.sending}
      setModelPickerOpen={modelControl.setModelPickerOpen}
      setQuotedContext={pageState.setQuotedContext}
      setQuoteSelection={pageState.setQuoteSelection}
      showBranchRestoreDivider={viewState.showBranchRestoreDivider}
      sidebarToggle={sidebarToggle}
      thinkingMode={modelControl.thinkingMode}
      uploadedResources={pageState.uploadedResources}
      uploadingResources={pageState.uploadingResources}
      visibleMessages={viewState.visibleMessages}
      workspaceTitle={viewState.workspaceTitle}
    />
  );
}
