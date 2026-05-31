import { useRef, useState } from "react";

import {
  type AddedModel,
  type ConversationDetail,
  type ConversationSummary,
  type UploadedResource
} from "../../api/client";
import { type UploadingResource } from "./contextResources";
import {
  type ActiveStream,
  type QuoteSelection,
  type QuotedContext,
  type ScenarioTab,
  type WorkspaceView
} from "./workspaceTypes";

export type HomeConversationDraft = {
  currentSessionId: string | null;
  conversationDetail: ConversationDetail | null;
  composerText: string;
  parentForNextMessage: string | null | undefined;
  quotedContext: QuotedContext | null;
  quoteSelection: QuoteSelection | null;
  uploadedResources: UploadedResource[];
  uploadingResources: UploadingResource[];
};

export function useConversationPageState() {
  const [activeView, setActiveView] = useState<WorkspaceView>("home");
  const [activeScenario, setActiveScenario] = useState<ScenarioTab>("home");
  const [composerText, setComposerText] = useState("");
  const [composerError, setComposerError] = useState("");
  const [sending, setSending] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [conversationDetail, setConversationDetail] = useState<ConversationDetail | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [models, setModels] = useState<AddedModel[]>([]);
  const [visionParseModel, setVisionParseModel] = useState<AddedModel | null>(null);
  const [uploadingResources, setUploadingResources] = useState<UploadingResource[]>([]);
  const [uploadedResources, setUploadedResources] = useState<UploadedResource[]>([]);
  const [parentForNextMessage, setParentForNextMessage] = useState<string | null | undefined>(undefined);
  const [quotedContext, setQuotedContext] = useState<QuotedContext | null>(null);
  const [quoteSelection, setQuoteSelection] = useState<QuoteSelection | null>(null);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const [activeStreamTurnId, setActiveStreamTurnId] = useState<string | null>(null);
  const [activelyThinkingTurnId, setActivelyThinkingTurnId] = useState<string | null>(null);
  const [cancellingTurnId, setCancellingTurnId] = useState<string | null>(null);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingMessageText, setEditingMessageText] = useState("");
  const [editingMessageContextResources, setEditingMessageContextResources] = useState<Array<Record<string, unknown>>>([]);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const messageRefs = useRef(new Map<string, HTMLElement>());
  const messageListRef = useRef<HTMLDivElement | null>(null);
  const conversationStageRef = useRef<HTMLDivElement | null>(null);
  const conversationSurfaceRef = useRef<HTMLDivElement | null>(null);
  const editingMessageInputRef = useRef<HTMLTextAreaElement | null>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const composerRef = useRef<HTMLFormElement | null>(null);
  const composerModelControlRef = useRef<HTMLDivElement | null>(null);
  const activeStreamRef = useRef<ActiveStream | null>(null);
  const conversationRequestSeqRef = useRef(0);
  const copySuccessTimeoutRef = useRef<number | null>(null);
  const homeConversationDraftRef = useRef<HomeConversationDraft | null>(null);

  return {
    activeStreamRef,
    activeStreamTurnId,
    activeView,
    activelyThinkingTurnId,
    cancellingTurnId,
    composerError,
    composerModelControlRef,
    composerRef,
    composerText,
    composerTextareaRef,
    conversationDetail,
    conversationRequestSeqRef,
    conversationStageRef,
    conversationSurfaceRef,
    conversations,
    copiedMessageId,
    copySuccessTimeoutRef,
    currentSessionId,
    editingMessageContextResources,
    editingMessageId,
    editingMessageInputRef,
    editingMessageText,
    highlightedMessageId,
    homeConversationDraftRef,
    messageListRef,
    messageRefs,
    models,
    parentForNextMessage,
    quotedContext,
    quoteSelection,
    sending,
    setActiveScenario,
    setActiveStreamTurnId,
    setActiveView,
    setActivelyThinkingTurnId,
    setCancellingTurnId,
    setComposerError,
    setComposerText,
    setConversationDetail,
    setConversations,
    setCopiedMessageId,
    setCurrentSessionId,
    setEditingMessageContextResources,
    setEditingMessageId,
    setEditingMessageText,
    setHighlightedMessageId,
    setModels,
    setParentForNextMessage,
    setQuoteSelection,
    setQuotedContext,
    setSending,
    setUploadedResources,
    setVisionParseModel,
    setUploadingResources,
    activeScenario,
    uploadedResources,
    uploadingResources,
    visionParseModel
  };
}
