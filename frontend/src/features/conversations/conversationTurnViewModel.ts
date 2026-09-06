import type {
  ConversationContextRecord,
  ConversationModelRecord,
  ConversationRecord,
  ConversationToolRecord
} from "../../api/client";
import type { WebCitationSource } from "../../utils/markdownCitations";
import {
  webCitationSourcesFromToolRecords
} from "./citations";
import {
  modelInputTextByResourceId,
  relatedReportResourcesForAssistant
} from "./conversationTurnPresentation";
import {
  groupConversationRecordsByTurn,
  type ConversationTurnGroup
} from "./conversationTurns";
import type { RelatedReportReference } from "./RelatedReports";

type ConversationTurnViewModel = ConversationTurnGroup & {
  active: boolean;
  citationSourcesByAssistantId: ReadonlyMap<string, readonly WebCitationSource[]>;
  contextInputTextByResourceId: Record<string, string>;
  modelResultRecords: ConversationModelRecord[];
  relatedReportsByAssistantId: ReadonlyMap<string, RelatedReportReference[]>;
  showExecution: boolean;
  usageAssistantId?: string;
};

export function buildConversationTurnViewModels(
  records: ConversationRecord[],
  activeStreamTurnId: string | null
): ConversationTurnViewModel[] {
  return groupConversationRecordsByTurn(records).map((turn) => {
    const modelResultRecords: ConversationModelRecord[] = [];
    const toolRecords: ConversationToolRecord[] = [];
    let currentUserInputRecord: ConversationContextRecord | undefined;

    turn.executionRecords.forEach((record) => {
      if (record.kind === "model" && record.channel === "result") {
        modelResultRecords.push(record);
      } else if (record.kind === "tool") {
        toolRecords.push(record);
      } else if (record.kind === "context" && record.context_type === "current_user_message") {
        currentUserInputRecord = record;
      }
    });

    const reportsByTurnId = new Map<string, RelatedReportReference[]>();
    const citationsByTurnId = new Map<string, readonly WebCitationSource[]>();
    const relatedReportsByAssistantId = new Map<string, RelatedReportReference[]>();
    const citationSourcesByAssistantId = new Map<string, readonly WebCitationSource[]>();
    let usageAssistantId: string | undefined;
    turn.assistantRecords.forEach((message) => {
      if (message.content.trim()) {
        usageAssistantId = message.message_id;
      }
      let reports = reportsByTurnId.get(message.turn_id);
      if (!reports) {
        reports = relatedReportResourcesForAssistant(message, toolRecords);
        reportsByTurnId.set(message.turn_id, reports);
      }
      relatedReportsByAssistantId.set(message.message_id, reports);

      let citations = citationsByTurnId.get(message.turn_id);
      if (!citations) {
        citations = webCitationSourcesFromToolRecords(toolRecords, message.turn_id);
        citationsByTurnId.set(message.turn_id, citations);
      }
      citationSourcesByAssistantId.set(message.message_id, citations);
    });

    const active = turn.turnIds.some((turnId) => turnId === activeStreamTurnId);
    return {
      ...turn,
      active,
      citationSourcesByAssistantId,
      contextInputTextByResourceId: modelInputTextByResourceId(currentUserInputRecord?.content),
      modelResultRecords,
      relatedReportsByAssistantId,
      showExecution: active || turn.executionRecords.length > 0 || turn.assistantRecords.length > 0,
      usageAssistantId
    };
  });
}
