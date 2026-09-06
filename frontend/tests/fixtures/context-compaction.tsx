import { useState } from "react";
import { createRoot } from "react-dom/client";
import type { ConversationContextRecord, ConversationModelRecord } from "../../src/api/types";
import { ConversationTurnExecution } from "../../src/features/conversations/ConversationTurnExecution";
import "../../src/styles/index.css";

const chunks: ConversationModelRecord[] = [1, 2].flatMap((step) => ([
  {
    record_id: `chunk_${step}_content`, call_id: `chunk_${step}`, kind: "model", channel: "content",
    turn_id: "turn-1", purpose: "context_compaction", step, model_id: "compact-model",
    summary_kind: step === 1 ? "history" : "turn_prefix",
    status: "completed", value: `摘要分块${step}`, source_event_seqs: [step + 1]
  },
  {
    record_id: `chunk_${step}_result`, call_id: `chunk_${step}`, kind: "model", channel: "result",
    turn_id: "turn-1", purpose: "context_compaction", step, model_id: "compact-model",
    summary_kind: step === 1 ? "history" : "turn_prefix",
    status: "completed", value: {}, usage: { prompt_tokens: 200, completion_tokens: 50 }, source_event_seqs: [step + 2]
  }
]));

function Fixture() {
  const [state, setState] = useState("running");
  const status: ConversationContextRecord = {
    record_id: "compaction_test", kind: "context", turn_id: "turn-1", call_id: "compaction_test",
    context_id: "compaction_test", context_type: "compaction_status", purpose: "context_compaction",
    label: "上下文压缩", status: state, content: null, source_event_seqs: [1],
    estimated_tokens_before: 80000, target_tokens: 60000,
    ...(state === "completed" ? { estimated_tokens_after: 52000 } : {}),
    ...(state === "failed" ? { error: { code: "INVALID_SUMMARY", message: "摘要为空" } } : {})
  };
  const records = [status, ...chunks];
  return <main style={{ padding: 16, width: "100%", maxWidth: 760 }}>
    <div>
      <button onClick={() => setState("completed")}>模拟提交</button>
      <button onClick={() => setState("failed")}>模拟失败</button>
    </div>
    <ConversationTurnExecution
      active activeTurnId="turn-1" highlightedMessageId={null} onRegisterMessageElement={() => {}}
      records={records} turnRecords={records} visibleBaseContextRecordIds={new Set()}
      visibleContextTypes={new Set()} visibleToolTypes={new Set()}
    />
  </main>;
}

createRoot(document.getElementById("root")!).render(<Fixture />);
