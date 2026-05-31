import type {
  ChangeEvent,
  Dispatch,
  FormEvent,
  MutableRefObject,
  ReactNode,
  RefObject,
  SetStateAction
} from "react";

import type {
  AddedModel,
  ConversationMessage,
  Favorite,
  UploadedResource
} from "../../api/client";
import { BranchControls } from "./BranchControls";
import { ComposerModelControl } from "./ComposerModelControl";
import { ConversationComposer } from "./ConversationComposer";
import { ConversationMessageBubble } from "./ConversationMessageBubble";
import { HealthWorkspacePlaceholder, HomeWorkspace } from "./HomeWorkspace";
import {
  quotePreviewText,
  type QuoteContextResource,
  type UploadingResource
} from "./contextResources";
import {
  QuoteContextChip,
  UploadedResourceChip,
  UploadingResourceChip
} from "./ResourceChips";
import { composerThinkingModeLabel, thinkingModeLabel } from "./thinking";
import type {
  QuoteSelection,
  QuotedContext,
  ScenarioCopy,
  ScenarioTab,
  WorkspaceView
} from "./workspaceTypes";

type ConversationWorkspaceSurfaceProps = {
  activeScenario: ScenarioTab;
  activeStreamTurnId: string | null;
  activeView: WorkspaceView;
  activelyThinkingTurnId: string | null;
  branchAfter: (message: ConversationMessage) => void;
  branchParentKey: (message: ConversationMessage) => string;
  canAttachFiles: boolean;
  cancellingTurnId: string | null;
  childrenByParent: Map<string, ConversationMessage[]>;
  chooseSessionModel: (modelId: string) => Promise<void> | void;
  chooseThinkingMode: (mode: string) => void;
  copiedMessageId: string | null;
  composerError: string;
  composerModelControlRef: RefObject<HTMLDivElement | null>;
  composerRef: RefObject<HTMLFormElement | null>;
  composerTextareaRef: RefObject<HTMLTextAreaElement | null>;
  composerText: string;
  conversationStageRef: RefObject<HTMLDivElement | null>;
  conversationSurfaceRef: RefObject<HTMLDivElement | null>;
  editingMessageContextResources: Array<Record<string, unknown>>;
  editingMessageId: string | null;
  editingMessageInputRef: RefObject<HTMLTextAreaElement | null>;
  editingMessageText: string;
  favorites: Favorite[];
  highlightedMessageId: string | null;
  messageListRef: RefObject<HTMLDivElement | null>;
  messageRefs: MutableRefObject<Map<string, HTMLElement>>;
  messagesLength: number;
  modelPickerOpen: boolean;
  models: AddedModel[];
  onAddSelectedTextToConversation: () => void;
  onCancelActiveGeneration: () => void | Promise<void>;
  onCancelEditingMessage: () => void;
  onComposerTextChange: Dispatch<SetStateAction<string>>;
  onConversationScroll: () => void;
  onCopyMessage: (message: ConversationMessage) => void | Promise<void>;
  onEditUserMessage: (message: ConversationMessage) => void;
  onEditingMessageTextChange: Dispatch<SetStateAction<string>>;
  onFileUpload: (event: ChangeEvent<HTMLInputElement>) => void | Promise<void>;
  onRegenerate: (message: ConversationMessage) => void | Promise<void>;
  onRemoveEditingContextResource: (resourceId: string) => void;
  onRemoveUploadedResource: (resourceId: string) => void;
  onRestoreBranchPreview: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void | Promise<void>;
  onSubmitEditedUserMessage: (
    event: FormEvent<HTMLFormElement>,
    message: ConversationMessage
  ) => void | Promise<void>;
  onSwitchBranch: (message: ConversationMessage, direction: -1 | 1) => void | Promise<void>;
  onToggleFavorite: (message: ConversationMessage) => void | Promise<void>;
  onUpdateQuoteSelection: (message: ConversationMessage) => void;
  parentForNextMessage: string | null | undefined;
  quoteSelection: QuoteSelection | null;
  quotedContext: QuotedContext | null;
  selectedModel: AddedModel | undefined;
  selectedModelFileMimeTypes: string[];
  selectedScenario: ScenarioCopy;
  selectedThinkingModes: string[];
  sending: boolean;
  setModelPickerOpen: Dispatch<SetStateAction<boolean>>;
  setQuotedContext: Dispatch<SetStateAction<QuotedContext | null>>;
  setQuoteSelection: Dispatch<SetStateAction<QuoteSelection | null>>;
  showBranchRestoreDivider: boolean;
  sidebarToggle: () => ReactNode;
  thinkingMode: string;
  uploadedResources: UploadedResource[];
  uploadingResources: UploadingResource[];
  visibleMessages: ConversationMessage[];
  workspaceTitle: string;
};

export function ConversationWorkspaceSurface({
  activeScenario,
  activeStreamTurnId,
  activeView,
  activelyThinkingTurnId,
  branchAfter,
  branchParentKey,
  canAttachFiles,
  cancellingTurnId,
  childrenByParent,
  chooseSessionModel,
  chooseThinkingMode,
  copiedMessageId,
  composerError,
  composerModelControlRef,
  composerRef,
  composerTextareaRef,
  composerText,
  conversationStageRef,
  conversationSurfaceRef,
  editingMessageContextResources,
  editingMessageId,
  editingMessageInputRef,
  editingMessageText,
  favorites,
  highlightedMessageId,
  messageListRef,
  messageRefs,
  messagesLength,
  modelPickerOpen,
  models,
  onAddSelectedTextToConversation,
  onCancelActiveGeneration,
  onCancelEditingMessage,
  onComposerTextChange,
  onConversationScroll,
  onCopyMessage,
  onEditUserMessage,
  onEditingMessageTextChange,
  onFileUpload,
  onRegenerate,
  onRemoveEditingContextResource,
  onRemoveUploadedResource,
  onRestoreBranchPreview,
  onSubmit,
  onSubmitEditedUserMessage,
  onSwitchBranch,
  onToggleFavorite,
  onUpdateQuoteSelection,
  parentForNextMessage,
  quoteSelection,
  quotedContext,
  selectedModel,
  selectedModelFileMimeTypes,
  selectedScenario,
  selectedThinkingModes,
  sending,
  setModelPickerOpen,
  setQuotedContext,
  setQuoteSelection,
  showBranchRestoreDivider,
  sidebarToggle,
  thinkingMode,
  uploadedResources,
  uploadingResources,
  visibleMessages,
  workspaceTitle
}: ConversationWorkspaceSurfaceProps) {
  function renderBranchRestoreDivider() {
    return (
      <button className="branch-restore-divider" onClick={onRestoreBranchPreview} type="button">
        <span>恢复分支前对话</span>
      </button>
    );
  }

  function renderBranchControls(message: ConversationMessage) {
    const siblings = childrenByParent.get(branchParentKey(message)) ?? [];
    const currentIndex = siblings.findIndex((sibling) => sibling.message_id === message.message_id);
    return (
      <BranchControls
        currentIndex={currentIndex}
        onSwitch={(direction) => void onSwitchBranch(message, direction)}
        siblingCount={siblings.length}
      />
    );
  }

  function renderComposerModelControl() {
    const currentModelName = selectedModel?.model_name ?? "未添加聊天模型";
    const currentThinkingLabel = composerThinkingModeLabel(thinkingMode);

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

  function registerMessageElement(messageId: string, node: HTMLElement | null) {
    if (node) {
      messageRefs.current.set(messageId, node);
    } else {
      messageRefs.current.delete(messageId);
    }
  }

  function renderMessageBubble(message: ConversationMessage) {
    if (shouldHideAssistantPlaceholderDuringThinking(message)) {
      return null;
    }

    return (
      <ConversationMessageBubble
        activelyThinkingTurnId={activelyThinkingTurnId}
        branchControls={renderBranchControls(message)}
        branchingFromThisMessage={parentForNextMessage === message.message_id}
        copied={copiedMessageId === message.message_id}
        editingMessageContextResources={editingMessageContextResources}
        editingMessageId={editingMessageId}
        editingMessageInputRef={editingMessageInputRef}
        editingMessageText={editingMessageText}
        favorited={favorites.some((favorite) => favorite.source_id === message.message_id)}
        highlightedMessageId={highlightedMessageId}
        key={message.message_id}
        message={message}
        onBranchAfter={branchAfter}
        onCancelEditingMessage={onCancelEditingMessage}
        onCopyMessage={onCopyMessage}
        onEditUserMessage={onEditUserMessage}
        onEditingMessageTextChange={onEditingMessageTextChange}
        onRegenerate={onRegenerate}
        onRegisterMessageElement={registerMessageElement}
        onRemoveEditingContextResource={onRemoveEditingContextResource}
        onSubmitEditedUserMessage={onSubmitEditedUserMessage}
        onToggleFavorite={onToggleFavorite}
        onUpdateQuoteSelection={onUpdateQuoteSelection}
        sending={sending}
      />
    );
  }

  function shouldHideAssistantPlaceholderDuringThinking(message: ConversationMessage) {
    return (
      message.role === "assistant" &&
      message.status === "streaming" &&
      !message.content &&
      activelyThinkingTurnId === message.turn_id
    );
  }

  function renderQuoteContextChip(quote: QuoteContextResource, removable: boolean) {
    return (
      <QuoteContextChip
        quote={quote}
        removable={removable}
        onRemove={() => {
          setQuotedContext(null);
          setQuoteSelection(null);
        }}
      />
    );
  }

  function renderUploadedResourceChip(resource: UploadedResource) {
    return (
      <UploadedResourceChip
        resource={resource}
        onRemove={onRemoveUploadedResource}
      />
    );
  }

  function renderUploadingResourceChip(resource: UploadingResource) {
    return <UploadingResourceChip resource={resource} />;
  }

  function renderConversationComposer() {
    return (
      <ConversationComposer
        activeScenario={activeScenario}
        activeStreamTurnId={activeStreamTurnId}
        canAttachFiles={canAttachFiles}
        cancellingTurnId={cancellingTurnId}
        composerError={composerError}
        composerRef={composerRef}
        composerTextareaRef={composerTextareaRef}
        composerText={composerText}
        onCancelActiveGeneration={() => void onCancelActiveGeneration()}
        onComposerTextChange={onComposerTextChange}
        onFileUpload={onFileUpload}
        onSubmit={onSubmit}
        quotedContext={
          quotedContext
            ? {
                resource_id: quotedContext.resource_id,
                quote_text: quotedContext.quote_text,
                preview: quotePreviewText(quotedContext.quote_text)
              }
            : null
        }
        renderComposerModelControl={renderComposerModelControl}
        renderQuoteContextChip={renderQuoteContextChip}
        renderUploadedResourceChip={renderUploadedResourceChip}
        renderUploadingResourceChip={renderUploadingResourceChip}
        selectedModelFileMimeTypes={selectedModelFileMimeTypes}
        selectedScenarioPlaceholder={selectedScenario.placeholder}
        sending={sending}
        uploadedResources={uploadedResources}
        uploadingResources={uploadingResources}
      />
    );
  }

  function renderMainWorkspace() {
    if (activeView === "health") {
      return <HealthWorkspacePlaceholder />;
    }

    return (
      <HomeWorkspace
        branchRestoreDivider={showBranchRestoreDivider ? renderBranchRestoreDivider() : null}
        composer={renderConversationComposer()}
        conversationStageRef={conversationStageRef}
        conversationSurfaceRef={conversationSurfaceRef}
        messageItems={visibleMessages.map((message) => renderMessageBubble(message))}
        messageListRef={messageListRef}
        messagesLength={messagesLength}
        onAddSelectedTextToConversation={onAddSelectedTextToConversation}
        onConversationScroll={onConversationScroll}
        quoteSelection={quoteSelection}
        sidebarToggle={sidebarToggle()}
        workspaceTitle={workspaceTitle}
      />
    );
  }

  return renderMainWorkspace();
}
