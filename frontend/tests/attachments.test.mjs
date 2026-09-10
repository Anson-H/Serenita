import assert from "node:assert/strict";
import test, { describe } from "node:test";
import { loadModule } from "./helpers/load-module.mjs";

describe("attachment-batch", () => {
  for (const partialFailure of [false, true]) test(`uploaded files retain their session when detail refresh fails; partial failure=${partialFailure}`, async () => {
    let session = null, resources = [], progress = [], message = '', uploads = 0;
    const { ConversationDraftStore } = loadModule('features/conversations/conversationDraftStore.ts');
    const draftStore = new ConversationDraftStore();
    draftStore.subscribe(() => { resources = draftStore.snapshot().uploadedResources; progress = draftStore.snapshot().uploadingResources; });
    const { useConversationAttachments } = loadModule('features/conversations/useConversationAttachments.ts', {}, {
      react: { useEffect() {} }, '../../utils/useActiveScope': { useActiveScope: () => () => true },
      '../members/MemberProvider': { useMembers: () => ({ activeMemberId: 'm' }) },
      '../../api/client': { apiClient: {
        uploadContextResource: async () => { uploads++; if (partialFailure && uploads === 2) throw new Error('failed-file');
          return { session_id: 'uploaded-session', resource: { resource_id: 'one', original_filename: 'one.png' } }; },
        getConversation: async () => { throw new Error('refresh failed'); }
      } }
    });
    const hook = useConversationAttachments({ draftStore, conversationDetail: null, currentSessionId: null,
      selectedModelId: 'model', selectedModelFileMimeTypes: ['image/png'], attachmentCapabilitiesReady: true,
      setComposerError: value => { message = value; }, setConversationDetail() {},
      setCurrentSessionId: value => { session = value; }, setUploadedResources: next => { resources = next(resources); },
      setUploadingResources: next => { progress = next(progress); }, uploadedResourcesLength: 0 });
    const files = [{ name: 'one.png' }, ...(partialFailure ? [{ name: 'two.png' }, { name: 'three.png' }] : [])];
    await hook.handleFileUpload({ currentTarget: { files, value: 'selection' } });
    assert.equal(session, 'uploaded-session'); assert.equal(resources.length, 1); assert.equal(progress.length, 0);
    assert.equal(uploads, partialFailure ? 2 : 1);
    assert.match(message, partialFailure ? /two.png.*1.*failed-file/ : /附件已上传/);
  });
});

describe("attachment-support", () => {
  const { canAttachFilesForScenario, filterResourcesByMimeTypes } = loadModule("features/conversations/attachmentSupport.ts");

  test("model and scenario capabilities determine whether attachments are available", () => {
    assert.equal(canAttachFilesForScenario("home", ["image/png"]), true);
    assert.equal(canAttachFilesForScenario("reports", ["image/png"]), true);
    assert.equal(canAttachFilesForScenario("lifestyle", ["image/png"]), false);
    assert.equal(canAttachFilesForScenario("home", []), false);
  });

  test("resource filtering preserves identity when no resource is removed", () => {
    const emptyResources = [];
    const supportedResources = [{ mime_type: "image/png", id: "keep" }];

    assert.equal(filterResourcesByMimeTypes(emptyResources, ["image/png"]), emptyResources);
    assert.equal(
      filterResourcesByMimeTypes(supportedResources, ["image/png"]),
      supportedResources
    );
    assert.deepEqual(
      filterResourcesByMimeTypes(
        [
          { mime_type: "image/png", id: "keep" },
          { mime_type: "application/pdf", id: "drop" }
        ],
        ["image/png"]
      ),
      [{ mime_type: "image/png", id: "keep" }]
    );
  });
});

describe("context-resource-upload", () => {
  const { parseContextResourceUploadResponse } = loadModule("api/contextResourceUpload.ts");

  function response(resourceOverrides = {}) {
    return {
      session_id: "session-1",
      resource: {
        resource_id: "报告.pdf",
        original_filename: "报告.pdf",
        mime_type: "application/pdf",
        size_bytes: 12,
        relative_path: "conversations/attachments/session-1/报告.pdf",
        sha256: "abc123",
        storage_status: "ready",
        lifecycle_status: "pending",
        expires_at: "2026-09-07T00:00:00+08:00",
        ...resourceOverrides
      }
    };
  }

  test("upload response accepts only ready pending resources with the current fields", () => {
    const valid = response();

    assert.equal(parseContextResourceUploadResponse(valid), valid);
    assert.throws(
      () => parseContextResourceUploadResponse(response({ storage_status: "writing" })),
      /上传响应无效/
    );
    assert.throws(
      () => parseContextResourceUploadResponse(response({ lifecycle_status: "attached" })),
      /上传响应无效/
    );
  });

  for (const field of ["storage_status", "lifecycle_status"]) {
    test(`upload response requires ${field}`, () => {
      const incomplete = response();
      delete incomplete.resource[field];
      assert.throws(() => parseContextResourceUploadResponse(incomplete), /上传响应无效/);
    });
  }
});
