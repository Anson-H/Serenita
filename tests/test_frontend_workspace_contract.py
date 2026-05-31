import pathlib
import subprocess
import textwrap
import unittest


class FrontendWorkspaceContractTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(__file__).resolve().parents[1]

    def source(self, relative_path: str) -> str:
        app_shell_tests = {
            "test_app_defines_login_main_and_favorites_routes",
            "test_app_has_login_page_and_main_workspace",
            "test_app_tsx_is_a_thin_route_shell_after_reorganization",
            "test_auth_routes_select_login_or_registration_mode",
            "test_route_helpers_live_under_app_routes",
            "test_workspace_brand_does_not_show_patient_ai_workspace_tagline",
        }
        if relative_path == "frontend/src/App.tsx" and self._testMethodName not in app_shell_tests:
            markdown_source = (self.root / "frontend/src/components/MarkdownContent.tsx").read_text(
                encoding="utf-8"
            )
            context_resources_source = (self.root / "frontend/src/features/conversations/contextResources.ts").read_text(
                encoding="utf-8"
            )
            workspace_types_source = (self.root / "frontend/src/features/conversations/workspaceTypes.ts").read_text(
                encoding="utf-8"
            )
            resource_chips_source = (self.root / "frontend/src/features/conversations/ResourceChips.tsx").read_text(
                encoding="utf-8"
            )
            home_workspace_source = (self.root / "frontend/src/features/conversations/HomeWorkspace.tsx").read_text(
                encoding="utf-8"
            )
            conversation_composer_source = (
                self.root / "frontend/src/features/conversations/ConversationComposer.tsx"
            ).read_text(encoding="utf-8")
            conversation_draft_source = (
                self.root / "frontend/src/features/conversations/conversationDraft.ts"
            ).read_text(encoding="utf-8")
            message_bubble_source = (
                self.root / "frontend/src/features/conversations/ConversationMessageBubble.tsx"
            ).read_text(encoding="utf-8")
            thinking_source = (self.root / "frontend/src/features/conversations/thinking.ts").read_text(
                encoding="utf-8"
            )
            streaming_messages_source = (
                self.root / "frontend/src/features/conversations/streamingMessages.ts"
            ).read_text(encoding="utf-8")
            conversation_layout_source = (
                self.root / "frontend/src/features/conversations/useConversationLayout.ts"
            ).read_text(encoding="utf-8")
            conversation_view_state_source_path = (
                self.root / "frontend/src/features/conversations/useConversationViewState.ts"
            )
            conversation_view_state_source = (
                conversation_view_state_source_path.read_text(encoding="utf-8")
                if conversation_view_state_source_path.exists()
                else ""
            )
            conversation_page_state_source_path = (
                self.root / "frontend/src/features/conversations/useConversationPageState.ts"
            )
            conversation_page_state_source = (
                conversation_page_state_source_path.read_text(encoding="utf-8")
                if conversation_page_state_source_path.exists()
                else ""
            )
            favorite_state_source = (self.root / "frontend/src/features/favorites/favoriteState.ts").read_text(
                encoding="utf-8"
            )
            favorite_tags_source = (self.root / "frontend/src/features/favorites/favoriteTags.ts").read_text(
                encoding="utf-8"
            )
            favorite_panel_source_path = self.root / "frontend/src/features/favorites/FavoritesWorkspacePanel.tsx"
            favorite_panel_source = (
                favorite_panel_source_path.read_text(encoding="utf-8")
                if favorite_panel_source_path.exists()
                else ""
            )
            favorite_workspace_source_path = self.root / "frontend/src/features/favorites/useFavoriteWorkspace.ts"
            favorite_workspace_source = (
                favorite_workspace_source_path.read_text(encoding="utf-8")
                if favorite_workspace_source_path.exists()
                else ""
            )
            favorite_list_alignment_source_path = self.root / "frontend/src/features/favorites/useFavoriteListAlignment.ts"
            favorite_list_alignment_source = (
                favorite_list_alignment_source_path.read_text(encoding="utf-8")
                if favorite_list_alignment_source_path.exists()
                else ""
            )
            favorite_message_actions_source_path = self.root / "frontend/src/features/favorites/useFavoriteMessageActions.ts"
            favorite_message_actions_source = (
                favorite_message_actions_source_path.read_text(encoding="utf-8")
                if favorite_message_actions_source_path.exists()
                else ""
            )
            workspace_route_shell_source_path = self.root / "frontend/src/app/WorkspaceRouteShell.tsx"
            workspace_route_shell_source = (
                workspace_route_shell_source_path.read_text(encoding="utf-8")
                if workspace_route_shell_source_path.exists()
                else ""
            )
            conversation_workspace_source_path = self.root / "frontend/src/features/conversations/useConversationWorkspace.ts"
            conversation_workspace_source = (
                conversation_workspace_source_path.read_text(encoding="utf-8")
                if conversation_workspace_source_path.exists()
                else ""
            )
            conversation_stream_source_path = (
                self.root / "frontend/src/features/conversations/useConversationStreamController.ts"
            )
            conversation_stream_source = (
                conversation_stream_source_path.read_text(encoding="utf-8")
                if conversation_stream_source_path.exists()
                else ""
            )
            conversation_message_actions_source_path = (
                self.root / "frontend/src/features/conversations/useConversationMessageActions.ts"
            )
            conversation_message_actions_source = (
                conversation_message_actions_source_path.read_text(encoding="utf-8")
                if conversation_message_actions_source_path.exists()
                else ""
            )
            conversation_branching_source_path = (
                self.root / "frontend/src/features/conversations/useConversationBranching.ts"
            )
            conversation_branching_source = (
                conversation_branching_source_path.read_text(encoding="utf-8")
                if conversation_branching_source_path.exists()
                else ""
            )
            conversation_attachments_source_path = (
                self.root / "frontend/src/features/conversations/useConversationAttachments.ts"
            )
            conversation_attachments_source = (
                conversation_attachments_source_path.read_text(encoding="utf-8")
                if conversation_attachments_source_path.exists()
                else ""
            )
            conversation_model_control_source_path = (
                self.root / "frontend/src/features/conversations/useConversationModelControl.ts"
            )
            conversation_model_control_source = (
                conversation_model_control_source_path.read_text(encoding="utf-8")
                if conversation_model_control_source_path.exists()
                else ""
            )
            conversation_lifecycle_source_path = (
                self.root / "frontend/src/features/conversations/useConversationLifecycle.ts"
            )
            conversation_lifecycle_source = (
                conversation_lifecycle_source_path.read_text(encoding="utf-8")
                if conversation_lifecycle_source_path.exists()
                else ""
            )
            conversation_surface_source_path = (
                self.root / "frontend/src/features/conversations/ConversationWorkspaceSurface.tsx"
            )
            conversation_surface_source = (
                conversation_surface_source_path.read_text(encoding="utf-8")
                if conversation_surface_source_path.exists()
                else ""
            )
            conversation_panel_source_path = (
                self.root / "frontend/src/features/conversations/ConversationWorkspacePanel.tsx"
            )
            conversation_panel_source = (
                conversation_panel_source_path.read_text(encoding="utf-8")
                if conversation_panel_source_path.exists()
                else ""
            )
            workspace_route_content_source_path = (
                self.root / "frontend/src/features/conversations/WorkspaceRouteContent.tsx"
            )
            workspace_route_content_source = (
                workspace_route_content_source_path.read_text(encoding="utf-8")
                if workspace_route_content_source_path.exists()
                else ""
            )
            workspace_page_model_source_path = (
                self.root / "frontend/src/features/conversations/useWorkspacePageModel.ts"
            )
            workspace_page_model_source = (
                workspace_page_model_source_path.read_text(encoding="utf-8")
                if workspace_page_model_source_path.exists()
                else ""
            )
            workspace_source = (self.root / "frontend/src/features/conversations/WorkspacePage.tsx").read_text(
                encoding="utf-8"
            )
            favorites_source = (self.root / "frontend/src/features/favorites/FavoritesWorkspace.tsx").read_text(
                encoding="utf-8"
            )
            combined_workspace_source = workspace_source
            return "\n".join(
                [
                    markdown_source,
                    context_resources_source,
                    workspace_types_source,
                    resource_chips_source,
                    home_workspace_source,
                    conversation_composer_source,
                    conversation_draft_source,
                    message_bubble_source,
                    thinking_source,
                    streaming_messages_source,
                    conversation_layout_source,
                    conversation_view_state_source,
                    conversation_page_state_source,
                    favorite_state_source,
                    favorite_tags_source,
                    favorite_panel_source,
                    favorites_source,
                    combined_workspace_source,
                    favorite_workspace_source,
                    favorite_list_alignment_source,
                    favorite_message_actions_source,
                    workspace_route_shell_source,
                    conversation_lifecycle_source,
                    conversation_workspace_source,
                    conversation_stream_source,
                    conversation_message_actions_source,
                    conversation_branching_source,
                    conversation_attachments_source,
                    conversation_model_control_source,
                    conversation_surface_source,
                    conversation_panel_source,
                    workspace_route_content_source,
                    workspace_page_model_source,
                ]
            )
        if relative_path == "frontend/src/styles.css" and self._testMethodName != "test_styles_are_split_by_frontend_surface":
            style_files = [
                "tokens.css",
                "base.css",
                "components.css",
                "shell.css",
                "auth.css",
                "conversations.css",
                "composer.css",
                "favorites.css",
                "settings.css",
                "responsive.css",
            ]
            return "\n".join(
                (self.root / "frontend" / "src" / "styles" / style_file).read_text(encoding="utf-8")
                for style_file in style_files
            )
        if relative_path == "frontend/src/features/settings/SettingsShell.tsx":
            settings_files = [
                "settingsTypes.ts",
                "SettingsView.tsx",
                "SettingsWorkspacePanel.tsx",
                "SettingsShell.tsx",
            ]
            return "\n".join(
                (self.root / "frontend" / "src" / "features" / "settings" / settings_file).read_text(encoding="utf-8")
                for settings_file in settings_files
                if (self.root / "frontend" / "src" / "features" / "settings" / settings_file).exists()
            )
        if relative_path == "frontend/src/features/settings/SettingsWorkspacePanel.tsx":
            settings_workspace_path = self.root / relative_path
            return (
                settings_workspace_path.read_text(encoding="utf-8")
                if settings_workspace_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/favorites/FavoritesWorkspacePanel.tsx":
            favorite_panel_path = self.root / relative_path
            return (
                favorite_panel_path.read_text(encoding="utf-8")
                if favorite_panel_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/favorites/useFavoriteWorkspace.ts":
            favorite_workspace_path = self.root / relative_path
            return favorite_workspace_path.read_text(encoding="utf-8") if favorite_workspace_path.exists() else ""
        if relative_path == "frontend/src/features/favorites/useFavoriteListAlignment.ts":
            favorite_list_alignment_path = self.root / relative_path
            return (
                favorite_list_alignment_path.read_text(encoding="utf-8")
                if favorite_list_alignment_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/favorites/useFavoriteMessageActions.ts":
            favorite_message_actions_path = self.root / relative_path
            return (
                favorite_message_actions_path.read_text(encoding="utf-8")
                if favorite_message_actions_path.exists()
                else ""
            )
        if relative_path == "frontend/src/app/WorkspaceRouteShell.tsx":
            workspace_route_shell_path = self.root / relative_path
            return (
                workspace_route_shell_path.read_text(encoding="utf-8")
                if workspace_route_shell_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/useConversationWorkspace.ts":
            conversation_workspace_path = self.root / relative_path
            return (
                conversation_workspace_path.read_text(encoding="utf-8")
                if conversation_workspace_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/useConversationStreamController.ts":
            conversation_stream_path = self.root / relative_path
            return (
                conversation_stream_path.read_text(encoding="utf-8")
                if conversation_stream_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/useConversationMessageActions.ts":
            conversation_message_actions_path = self.root / relative_path
            return (
                conversation_message_actions_path.read_text(encoding="utf-8")
                if conversation_message_actions_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/useConversationBranching.ts":
            conversation_branching_path = self.root / relative_path
            return (
                conversation_branching_path.read_text(encoding="utf-8")
                if conversation_branching_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/useConversationAttachments.ts":
            conversation_attachments_path = self.root / relative_path
            return (
                conversation_attachments_path.read_text(encoding="utf-8")
                if conversation_attachments_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/useConversationViewState.ts":
            conversation_view_state_path = self.root / relative_path
            return (
                conversation_view_state_path.read_text(encoding="utf-8")
                if conversation_view_state_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/useConversationPageState.ts":
            conversation_page_state_path = self.root / relative_path
            return (
                conversation_page_state_path.read_text(encoding="utf-8")
                if conversation_page_state_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/useConversationModelControl.ts":
            conversation_model_control_path = self.root / relative_path
            return (
                conversation_model_control_path.read_text(encoding="utf-8")
                if conversation_model_control_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/useConversationLifecycle.ts":
            conversation_lifecycle_path = self.root / relative_path
            return (
                conversation_lifecycle_path.read_text(encoding="utf-8")
                if conversation_lifecycle_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/ConversationWorkspaceSurface.tsx":
            conversation_surface_path = self.root / relative_path
            return (
                conversation_surface_path.read_text(encoding="utf-8")
                if conversation_surface_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/ConversationWorkspacePanel.tsx":
            conversation_panel_path = self.root / relative_path
            return (
                conversation_panel_path.read_text(encoding="utf-8")
                if conversation_panel_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/WorkspaceRouteContent.tsx":
            workspace_route_content_path = self.root / relative_path
            return (
                workspace_route_content_path.read_text(encoding="utf-8")
                if workspace_route_content_path.exists()
                else ""
            )
        if relative_path == "frontend/src/features/conversations/useWorkspacePageModel.ts":
            workspace_page_model_path = self.root / relative_path
            return (
                workspace_page_model_path.read_text(encoding="utf-8")
                if workspace_page_model_path.exists()
                else ""
            )
        return (self.root / relative_path).read_text(encoding="utf-8")

    def message_bubble_source(self) -> str:
        return self.source("frontend/src/features/conversations/ConversationMessageBubble.tsx")

    def conversation_composer_source(self) -> str:
        return self.source("frontend/src/features/conversations/ConversationComposer.tsx")

    def home_workspace_source(self) -> str:
        return self.source("frontend/src/features/conversations/HomeWorkspace.tsx")

    def test_premium_visual_system_tokens_are_defined(self):
        styles_source = self.source("frontend/src/styles.css")

        for expected in [
            "--surface-strong",
            "--surface-raised",
            "--accent-strong",
            "--accent-soft",
            "--focus-ring",
            "--shadow-panel",
            "--radius-panel",
            "--transition-fast",
        ]:
            self.assertIn(expected, styles_source)
        self.assertIn("--back-button-size: 30px;", styles_source)
        self.assertIn(".patient-shell::before", styles_source)
        self.assertIn(".composer-model-popover", styles_source)

    def test_workspace_titlebars_share_stable_height_and_action_slots(self):
        styles_source = self.source("frontend/src/styles.css")
        favorites_source = self.source("frontend/src/features/favorites/FavoritesWorkspace.tsx")

        self.assertIn("--workspace-titlebar-height: 52px;", styles_source)
        self.assertIn("--workspace-titlebar-side: 44px;", styles_source)

        for selector in [
            ".favorites-workspace .favorite-toolbar {",
            ".settings-workspace .settings-toolbar {",
        ]:
            toolbar_source = styles_source.split(selector, 1)[1].split("}", 1)[0]
            self.assertIn("grid-template-columns: minmax(var(--workspace-titlebar-side), 1fr) auto minmax(var(--workspace-titlebar-side), 1fr);", toolbar_source)
            self.assertIn("height: var(--workspace-titlebar-height);", toolbar_source)
            self.assertIn("min-height: var(--workspace-titlebar-height);", toolbar_source)
            self.assertIn("padding: 0 12px;", toolbar_source)
            self.assertIn("border: 0;", toolbar_source)
            self.assertIn("border-bottom:", toolbar_source)
            self.assertIn("border-radius: 0;", toolbar_source)
            self.assertIn("background: transparent;", toolbar_source)

        mobile_header_source = styles_source.rsplit(
            ".settings-workspace .settings-mobile-layer-header {",
            1,
        )[1].split("}", 1)[0]
        mobile_media_source = styles_source.rsplit("@media (max-width: 650px)", 1)[1].split(
            "@media",
            1,
        )[0]
        self.assertIn("grid-template-columns: var(--workspace-titlebar-side) minmax(0, 1fr) var(--workspace-titlebar-side);", mobile_header_source)
        self.assertIn("height: var(--workspace-titlebar-height);", mobile_header_source)
        self.assertIn("min-height: var(--workspace-titlebar-height);", mobile_header_source)
        self.assertIn(".favorite-toolbar .sidebar-toggle-button {", mobile_media_source)
        self.assertIn("width: var(--back-button-size);", mobile_media_source)
        self.assertIn("min-width: var(--back-button-size);", mobile_media_source)

        self.assertIn("const favoriteToolbar =", favorites_source)
        self.assertIn("{favoriteToolbar}", favorites_source)
        self.assertLess(
            favorites_source.index("{favoriteToolbar}"),
            favorites_source.index('className="favorite-layout"'),
        )
        self.assertLess(
            favorites_source.index("{favoriteToolbar}"),
            favorites_source.index("favorite-empty-state"),
        )

    def test_frontend_styles_prune_legacy_cross_surface_overrides(self):
        styles_source = self.source("frontend/src/styles.css")
        favorites_styles = self.source("frontend/src/styles/favorites.css")
        conversations_styles = self.source("frontend/src/styles/conversations.css")

        for legacy_fragment in [
            "Migrated",
            "--line: #000000;",
            "--line-strong: #000000;",
            "border: 1px solid #000000;",
            "grid-template-columns: minmax(34px, 1fr) auto minmax(34px, 1fr);",
            "grid-template-columns: minmax(44px, 1fr) auto minmax(44px, 1fr);",
            "grid-template-columns: 48px minmax(0, 1fr) 48px;",
        ]:
            self.assertNotIn(legacy_fragment, styles_source)

        for cross_surface_selector in [
            ".message-bubble",
            ".message-actions",
            ".message-edit-actions",
            ".branch-controls",
            ".resource-list",
        ]:
            self.assertNotIn(cross_surface_selector, favorites_styles)

        self.assertNotIn(".favorite-toolbar", conversations_styles)

    def test_home_composer_uses_deepseek_style_icon_controls(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertNotIn("首页对话", app_source)
        self.assertIn('className="assistant-composer conversation-composer"', app_source)
        self.assertIn('className="file-button icon-button"', app_source)
        self.assertIn('aria-label="附加文件"', app_source)
        self.assertIn("PaperclipIcon", app_source)
        self.assertIn("ArrowUpIcon", app_source)
        self.assertIn("StopIcon", app_source)
        self.assertIn('className="command-button send-button"', app_source)
        self.assertIn('className="command-button send-button stop-button"', app_source)
        self.assertIn('aria-label={sending ? "发送中..." : "发送"}', app_source)
        self.assertIn('aria-label="停止生成"', app_source)
        self.assertIn(".conversation-composer", styles_source)
        self.assertIn("padding: 16px 16px 12px;", styles_source)
        self.assertIn("min-height: 104px;", styles_source)
        self.assertIn(".icon-button", styles_source)
        self.assertIn("width: 38px;", styles_source)
        self.assertIn("min-height: 38px;", styles_source)
        self.assertIn(".send-button", styles_source)
        self.assertIn(".stop-button", styles_source)
        self.assertIn(".stop-icon", styles_source)
        self.assertIn(
            ".conversation-composer .composer-model-trigger {\n"
            "  width: max-content;\n"
            "  max-width: 100%;\n"
            "  min-height: 38px;",
            styles_source,
        )
        self.assertIn("grid-template-columns: auto auto auto", styles_source)

    def test_attachment_button_depends_on_selected_model_file_capabilities(self):
        app_source = self.source("frontend/src/App.tsx")
        attachments_source = self.source("frontend/src/features/conversations/useConversationAttachments.ts")
        view_state_source = self.source("frontend/src/features/conversations/useConversationViewState.ts")
        page_state_source = self.source("frontend/src/features/conversations/useConversationPageState.ts")
        conversation_api_source = self.source("frontend/src/api/conversationApi.ts")

        self.assertIn(
            'import { canAttachFilesForScenario, mergeModelFileMimeTypes } from "./attachmentSupport";',
            view_state_source,
        )
        self.assertIn('import { filterResourcesByMimeTypes } from "./attachmentSupport";', attachments_source)
        self.assertIn("const [visionParseModel, setVisionParseModel] = useState<AddedModel | null>(null)", page_state_source)
        self.assertIn("const selectedModelFileMimeTypes = mergeModelFileMimeTypes(selectedModel, visionParseModel)", view_state_source)
        self.assertIn("const canAttachFiles = canAttachFilesForScenario(activeScenario, selectedModelFileMimeTypes)", view_state_source)
        self.assertIn("{canAttachFiles ? (", app_source)
        self.assertIn('accept={selectedModelFileMimeTypes.join(",")}', app_source)
        self.assertIn("selectedModelId: selectedModel?.model_id ?? null", app_source)
        self.assertIn(
            "apiClient.uploadContextResource(currentSessionId, file, selectedModelId, handleUploadProgress)",
            app_source,
        )
        self.assertIn("formData.append(\"model_id\", modelId ?? \"\")", conversation_api_source)
        self.assertIn("onUploadProgress?: (progress: number) => void", conversation_api_source)
        self.assertIn("const xhr = new XMLHttpRequest();", conversation_api_source)
        self.assertIn("xhr.upload.onprogress", conversation_api_source)
        self.assertIn("setUploadedResources((current) =>", app_source)
        self.assertIn("filterResourcesByMimeTypes(current, selectedModelFileMimeTypes)", attachments_source)

    def test_uploaded_files_render_as_removable_composer_chips(self):
        app_source = self.source("frontend/src/App.tsx")
        resource_chips_source = self.source("frontend/src/features/conversations/ResourceChips.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("function renderUploadedResourceChip", app_source)
        self.assertIn("file-context-chip", resource_chips_source)
        self.assertIn('aria-label={`附件：${resource.name}`}', resource_chips_source)
        self.assertIn("setUploadedResources((current) => current.filter((item) => item.resource_id !== resourceId))", app_source)
        composer_source = app_source.split('className="assistant-composer conversation-composer"', 1)[1].split(
            'className="composer-footer"',
            1,
        )[0]
        self.assertLess(
            composer_source.index("{uploadingResources.length || uploadedResources.length ? ("),
            composer_source.index('className="composer-input-frame"'),
        )
        self.assertIn("renderUploadedResourceChip(resource)", composer_source)
        self.assertNotIn("<span key={resource.resource_id}>{resource.name}</span>", composer_source)
        self.assertIn(".file-context-chip", styles_source)
        self.assertIn(".file-context-remove", styles_source)

    def test_uploading_files_render_progress_before_attachment_name(self):
        app_source = self.source("frontend/src/App.tsx")
        resource_chips_source = self.source("frontend/src/features/conversations/ResourceChips.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("type UploadingResource", app_source)
        self.assertIn("uploadingResources", app_source)
        self.assertIn("function renderUploadingResourceChip", app_source)
        self.assertIn('role="progressbar"', resource_chips_source)
        self.assertIn('className="file-upload-progress"', resource_chips_source)
        self.assertIn('aria-label={`正在上传：${resource.name}`}', resource_chips_source)
        upload_chip_source = resource_chips_source.split("function UploadingResourceChip", 1)[1].split(
            "type MessageQuoteReferenceProps",
            1,
        )[0]
        self.assertLess(
            upload_chip_source.index('className="file-upload-progress"'),
            upload_chip_source.index('className="file-context-name"'),
        )
        composer_source = app_source.split('className="assistant-composer conversation-composer"', 1)[1].split(
            'className="composer-input-frame"',
            1,
        )[0]
        self.assertIn("uploadingResources.map((resource) => renderUploadingResourceChip(resource))", composer_source)
        self.assertIn(".file-upload-progress", styles_source)
        self.assertIn("--upload-progress", styles_source)

    def test_composer_allows_attachment_only_send_without_empty_text_prompt(self):
        app_source = self.source("frontend/src/App.tsx")
        draft_source = self.source("frontend/src/features/conversations/conversationDraft.ts")
        send_source = app_source.split("async function sendMessage", 1)[1].split(
            "async function handleFileUpload",
            1,
        )[0]

        self.assertIn("submittedContextResourcesFromDraft(uploadedResources, quotedContext)", send_source)
        self.assertIn("if (!hasSubmittableDraft(trimmedText, submittedContextResources))", send_source)
        self.assertNotIn('setComposerError("请输入问题后再发送。")', send_source)
        self.assertIn("rawText: trimmedText", send_source)
        self.assertIn("uploadedResources.map((resource) => ({", draft_source)
        self.assertIn("quote_text: quotedContext.quote_text", draft_source)
        self.assertIn("return Boolean(rawText.trim() || contextResources.length);", draft_source)

    def test_attachment_support_helpers_execute_model_and_resource_capability_logic(self):
        script = textwrap.dedent(
            """
            const fs = require("fs");
            const path = require("path");
            const vm = require("vm");

            const helperPath = path.join(process.cwd(), "frontend", "src", "features", "conversations", "attachmentSupport.ts");
            const typescriptPath = path.join(process.cwd(), "frontend", "node_modules", "typescript");
            let ts;
            try {
              ts = require(typescriptPath);
            } catch (error) {
              throw new Error(`Unable to load TypeScript from ${typescriptPath}: ${error.message}`);
            }

            const source = fs.readFileSync(helperPath, "utf8");
            const transpiled = ts.transpileModule(source, {
              compilerOptions: {
                module: ts.ModuleKind.CommonJS,
                target: ts.ScriptTarget.ES2020
              },
              fileName: helperPath
            }).outputText;

            const module = { exports: {} };
            vm.runInNewContext(transpiled, { module, exports: module.exports, require }, { filename: helperPath });

            const {
              canAttachFilesForScenario,
              filterResourcesByMimeTypes,
              modelFileMimeTypes
            } = module.exports;

            function assertDeepEqual(actual, expected, label) {
              const actualJson = JSON.stringify(actual);
              const expectedJson = JSON.stringify(expected);
              if (actualJson !== expectedJson) {
                throw new Error(`${label}: expected ${expectedJson}, received ${actualJson}`);
              }
            }

            function assertEqual(actual, expected, label) {
              if (actual !== expected) {
                throw new Error(`${label}: expected ${expected}, received ${actual}`);
              }
            }

            assertDeepEqual(modelFileMimeTypes(null), [], "null model falls back to no MIME types");
            assertDeepEqual(
              modelFileMimeTypes({ file_mime_types: ["image/png"] }),
              ["image/png"],
              "model MIME types pass through"
            );
            assertEqual(canAttachFilesForScenario("home", ["image/png"]), true, "home accepts supported MIME types");
            assertEqual(canAttachFilesForScenario("reports", ["image/png"]), false, "non-home scenarios reject attachments");
            assertEqual(canAttachFilesForScenario("home", []), false, "home without MIME types rejects attachments");

            const emptyResources = [];
            assertEqual(
              filterResourcesByMimeTypes(emptyResources, ["image/png"]),
              emptyResources,
              "empty resources preserve array reference"
            );

            assertDeepEqual(
              filterResourcesByMimeTypes(
                [
                  { mime_type: "image/png", id: "keep" },
                  { mime_type: "application/pdf", id: "drop" }
                ],
                ["image/png"]
              ),
              [{ mime_type: "image/png", id: "keep" }],
              "resources filter by supported MIME type"
            );
            """
        )
        try:
            result = subprocess.run(
                ["node", "-e", script],
                cwd=self.root,
                capture_output=True,
                check=False,
                text=True,
            )
        except FileNotFoundError as error:
            self.fail(f"Node is required to execute attachment helper behavior test: {error}")

        self.assertEqual(
            result.returncode,
            0,
            f"Node helper behavior test failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )

    def test_home_composer_controls_use_token_borders_without_inner_textarea_box(self):
        styles_source = self.source("frontend/src/styles.css")

        def rule_body(selector: str) -> str:
            marker = f"{selector} {{\n"
            self.assertIn(marker, styles_source)
            return styles_source.rsplit(marker, 1)[1].split("}", 1)[0]

        textarea_source = rule_body(".conversation-composer textarea")
        file_button_source = rule_body(".conversation-composer .file-button")
        model_trigger_source = rule_body(".conversation-composer .composer-model-trigger")
        text_button_source = rule_body(".conversation-composer .text-button")
        quiet_control_source = styles_source.split(
            ".conversation-composer .file-button,\n"
            ".conversation-composer .composer-model-trigger,\n"
            ".conversation-composer .text-button,\n"
            ".file-button,",
            1,
        )[1].split("}", 1)[0]

        for control_source in (file_button_source, model_trigger_source, text_button_source):
            self.assertNotIn("border: 1px solid var(--line);", control_source)
        self.assertIn("border-color: transparent;", quiet_control_source)
        self.assertIn("border: 0;", textarea_source)
        self.assertNotIn("border: 1px solid var(--line);", textarea_source)
        self.assertIn(".send-button {\n  border-color: transparent;", styles_source)
        self.assertIn(".stop-button {\n  border-color: transparent;", styles_source)

    def test_app_defines_login_main_and_favorites_routes(self):
        app_source = self.source("frontend/src/App.tsx")
        auth_source = self.source("frontend/src/features/auth/AuthPage.tsx")
        routes_source = self.source("frontend/src/app/routes.ts")
        sidebar_source = self.source("frontend/src/app/Sidebar.tsx")
        session_source = self.source("frontend/src/features/auth/useAuthSession.ts")

        self.assertIn('SIGN_IN_PATH = "/sign_in"', routes_source)
        self.assertIn('SIGN_UP_PATH = "/sign_up"', routes_source)
        self.assertIn('APP_PATH = "/"', routes_source)
        self.assertIn('FAVORITES_PATH = "/favorites"', routes_source)
        self.assertIn('SETTING_PATH = "/setting"', routes_source)
        self.assertNotIn('SETTINGS_PATH = "/settings"', routes_source)
        self.assertNotIn('APP_PATH = "/app"', routes_source)
        self.assertNotIn('"/app"', routes_source)
        self.assertIn('from "./app/routes"', app_source)
        self.assertIn("useAuthSession", app_source)
        self.assertIn("checkSession", session_source)
        self.assertIn("renderRoute", app_source)
        self.assertIn("onNavigate={navigateTo}", app_source)
        self.assertIn("onNavigate(FAVORITES_PATH)", sidebar_source)
        self.assertIn("onNavigate(SETTING_PATH)", sidebar_source)
        self.assertIn("navigateTo(SIGN_IN_PATH, true)", app_source)
        self.assertIn("onModeChange(SIGN_UP_PATH)", auth_source)

    def test_auth_routes_select_login_or_registration_mode(self):
        app_source = self.source("frontend/src/App.tsx")
        auth_source = self.source("frontend/src/features/auth/AuthPage.tsx")

        self.assertIn('mode={route === SIGN_UP_PATH ? "sign_up" : "sign_in"}', app_source)
        self.assertIn("setAuthMode(mode)", auth_source)
        self.assertIn("onModeChange(SIGN_IN_PATH)", auth_source)
        self.assertIn("onModeChange(SIGN_UP_PATH)", auth_source)

    def test_frontend_auth_client_uses_sign_endpoint_names(self):
        auth_api_source = (self.root / "frontend" / "src" / "api" / "authApi.ts").read_text(
            encoding="utf-8"
        )
        session_token_source = (
            self.root / "frontend" / "src" / "api" / "sessionToken.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("function signUp", auth_api_source)
        self.assertIn('"/auth/sign_up"', auth_api_source)
        self.assertIn("function signIn", auth_api_source)
        self.assertIn('"/auth/sign_in"', auth_api_source)
        self.assertIn("function signOut", auth_api_source)
        self.assertIn('"/auth/sign_out"', auth_api_source)
        self.assertIn('"serenita_auth_session_token"', session_token_source)

    def test_api_client_explains_vite_proxy_500_as_backend_unavailable(self):
        request_source = (self.root / "frontend" / "src" / "api" / "request.ts").read_text(
            encoding="utf-8"
        )
        conversation_api_source = (
            self.root / "frontend" / "src" / "api" / "conversationApi.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("function serverFailureMessage", request_source)
        self.assertIn("后端服务返回 ${response.status}", request_source)
        self.assertIn("请检查后端终端日志", request_source)
        self.assertIn("serverFailureMessage(response)", request_source)
        self.assertIn("serverFailureMessage(response)", conversation_api_source)

    def test_api_error_copy_mentions_current_page_for_test_ports(self):
        vite_source = (self.root / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
        request_source = (self.root / "frontend" / "src" / "api" / "request.ts").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("preview:", vite_source)
        self.assertIn("port: 5173", vite_source)
        self.assertIn("127.0.0.1:8000", request_source)
        self.assertIn("VITE_API_BASE_URL", request_source)
        self.assertIn("当前页面地址", request_source)
        self.assertIn("临时预览或测试端口", request_source)
        self.assertIn("切回 5173", request_source)

    def test_app_has_login_page_and_main_workspace(self):
        app_source = self.source("frontend/src/App.tsx")
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        conversation_surface_source = self.source(
            "frontend/src/features/conversations/ConversationWorkspaceSurface.tsx"
        )
        conversation_panel_source = self.source(
            "frontend/src/features/conversations/ConversationWorkspacePanel.tsx"
        )
        route_content_source = self.source(
            "frontend/src/features/conversations/WorkspaceRouteContent.tsx"
        )
        auth_source = self.source("frontend/src/features/auth/AuthPage.tsx")
        shell_source = self.source("frontend/src/app/PatientShell.tsx")

        self.assertIn("AuthPage", app_source)
        self.assertIn("login-page", auth_source)
        self.assertIn("login-form", auth_source)
        self.assertIn("register-form", auth_source)
        self.assertIn("main-page", shell_source)
        self.assertIn("WorkspaceRouteContent", workspace_source)
        self.assertIn("ConversationWorkspacePanel", route_content_source)
        self.assertIn("ConversationWorkspaceSurface", conversation_panel_source)
        self.assertIn("ConversationComposer", conversation_surface_source)
        self.assertIn("assistant-composer", self.conversation_composer_source())
        self.assertIn("HomeWorkspace", conversation_surface_source)
        self.assertIn("workspace-titlebar", self.home_workspace_source())
        self.assertIn("conversation-surface", self.home_workspace_source())

    def test_sidebar_scenarios_and_chat_title_use_current_conversation_title(self):
        app_source = self.source("frontend/src/App.tsx")
        hook_source = self.source("frontend/src/app/useResponsiveSidebar.ts")
        shell_source = self.source("frontend/src/app/PatientShell.tsx")
        sidebar_source = self.source("frontend/src/app/Sidebar.tsx")
        view_state_source = self.source("frontend/src/features/conversations/useConversationViewState.ts")
        styles_source = self.source("frontend/src/styles.css")

        scenario_nav_source = sidebar_source.split('className="sidebar-scenario-nav"', 1)[1].split(
            'className="primary-action"',
            1,
        )[0]
        self.assertIn("mobileSidebarOpen", app_source)
        self.assertIn("setMobileSidebarOpen", hook_source)
        self.assertIn("sidebarCollapsed", app_source)
        self.assertIn("setSidebarCollapsed", hook_source)
        brand_row_source = sidebar_source.split('className="brand-row"', 1)[1].split(
            "</section>",
            1,
        )[0]
        self.assertIn("function toggleSidebarFromMain", hook_source)
        self.assertIn("function collapseSidebarFromSidebar", hook_source)
        self.assertIn("showWorkspaceSidebarToggle", app_source)
        self.assertIn('className="sidebar-collapse-button"', brand_row_source)
        self.assertIn("onClick={onCollapseSidebar}", brand_row_source)
        self.assertIn('"sidebar-toggle-button"', app_source)
        self.assertIn("onClick={toggleSidebarFromMain}", app_source)
        self.assertIn("if (!showWorkspaceSidebarToggle)", app_source)
        self.assertIn("sidebarToggle={() => workspaceShell.renderSidebarToggle()}", app_source)
        self.assertIn("sidebarToggle={sidebarToggle()}", app_source)
        self.assertIn("sidebarScenarioTabs.map", sidebar_source)
        self.assertIn('"sidebar-scenario-tab active" : "sidebar-scenario-tab"', sidebar_source)
        self.assertIn('aria-label={`切换到${scenarioLabel(scenario)}`}', scenario_nav_source)
        self.assertIn("onClick={() => openScenarioFromSidebar(scenario)}", scenario_nav_source)
        self.assertNotIn('className="sidebar-toggle-button"', shell_source)
        self.assertIn('data-mobile-sidebar-open={mobileSidebarOpen ? "true" : "false"}', shell_source)
        self.assertIn('data-sidebar-collapsed={sidebarCollapsed ? "true" : "false"}', shell_source)
        self.assertIn(
            'const workspaceTitle = activeScenario === "home" && conversationDetail ? conversationDetail.title : selectedScenario.title',
            view_state_source,
        )
        self.assertIn("<h1>{workspaceTitle}</h1>", app_source)
        self.assertNotIn("健康咨询", app_source)
        self.assertIn(".sidebar-scenario-nav", styles_source)
        self.assertIn("justify-self: stretch", styles_source)
        self.assertIn("width: 100%;", styles_source)
        self.assertIn(".sidebar-toggle-button,\n.sidebar-collapse-button", styles_source)
        self.assertIn(".workspace-titlebar-side", styles_source)
        self.assertIn("justify-self: start;", styles_source)
        self.assertIn(".sidebar-collapse-button", styles_source)
        self.assertNotIn(".sidebar-toggle-button {\n  display: none;", styles_source)
        self.assertIn('@media (max-width: 1000px)', styles_source)
        self.assertIn("  .sidebar-toggle-button,\n  .mobile-sidebar-close-button {\n    display: inline-grid;", styles_source)
        self.assertIn("  .sidebar-collapse-button {\n    display: none;", styles_source)
        self.assertNotIn(".workspace-tabs", styles_source)

    def test_streaming_turn_keeps_new_conversation_title_until_completion(self):
        app_source = self.source("frontend/src/App.tsx")
        streaming_source = app_source.split("function showStreamingTurn", 1)[1].split(
            "function showRegeneratingTurn",
            1,
        )[0]

        self.assertNotIn("function previewConversationTitle", app_source)
        self.assertIn(": UNTITLED_CONVERSATION_TITLE", streaming_source)
        self.assertNotIn("previewConversationTitle(rawText)", streaming_source)
        self.assertNotIn("rawText.slice(0, 20)", streaming_source)

    def test_pending_new_conversation_appears_in_sidebar_as_new_chat(self):
        app_source = self.source("frontend/src/App.tsx")
        submit_source = app_source.split("async function submitConversationMessage", 1)[1].split(
            "async function sendMessage",
            1,
        )[0]

        self.assertIn("function showPendingConversationSummary", app_source)
        self.assertIn("title: UNTITLED_CONVERSATION_TITLE", app_source)
        self.assertIn("showPendingConversationSummary(response, input.rawText)", submit_source)
        self.assertLess(
            submit_source.index("showPendingConversationSummary(response, input.rawText)"),
            submit_source.index("startResponseStream(response)"),
        )

    def test_composer_only_uses_status_text_for_errors(self):
        app_source = self.source("frontend/src/App.tsx")

        self.assertNotIn('setComposerError("已', app_source)
        self.assertNotIn("会话已删除，收藏快照不会受影响。", app_source)
        self.assertNotIn("已选定分支起点", app_source)
        self.assertNotIn("已添加历史消息引用", app_source)

    def test_workspace_brand_does_not_show_patient_ai_workspace_tagline(self):
        app_source = self.source("frontend/src/App.tsx")

        self.assertIn('<div className="brand-name">Serenita</div>', app_source)
        self.assertNotIn("患者端 AI 健康工作台", app_source)
        self.assertNotIn("登录后进入患者端 AI 健康工作台", app_source)

    def test_register_form_explains_account_and_password_rules(self):
        auth_source = self.source("frontend/src/features/auth/AuthPage.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("registration-guidance", auth_source)
        self.assertIn("账号：1-20 位英文、数字、下划线或短横线", auth_source)
        self.assertIn("密码：不能为空，请妥善保存", auth_source)
        self.assertIn("确认密码必须完全一致", auth_source)
        self.assertIn(".registration-guidance", styles_source)

    def test_setting_page_has_stateful_internal_sections(self):
        settings_source = self.source("frontend/src/features/settings/SettingsShell.tsx")
        settings_workspace_source = self.source("frontend/src/features/settings/SettingsWorkspacePanel.tsx")
        app_source = self.source("frontend/src/App.tsx")
        routes_source = self.source("frontend/src/app/routes.ts")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("typeof SETTING_PATH", routes_source)
        self.assertIn("window.location.pathname === SETTING_PATH", routes_source)
        self.assertIn("SettingsWorkspacePanel", app_source)
        self.assertIn("export function SettingsWorkspacePanel", settings_workspace_source)
        self.assertIn('className="workspace-panel settings-workspace"', settings_workspace_source)
        self.assertNotIn("settingsOpen", app_source)
        self.assertNotIn("setSettingsOpen", app_source)
        self.assertNotIn("function renderSettingsModal()", app_source)
        self.assertNotIn('className="settings-modal-backdrop"', app_source)
        self.assertNotIn('className="settings-modal"', app_source)
        self.assertIn("activeSection", settings_source)
        self.assertIn("setActiveSection", settings_source)
        self.assertIn("account-feedback", settings_source)
        self.assertIn("provider-panel", settings_source)
        self.assertIn("settings-three-column", settings_source)
        self.assertIn("settings-primary-nav", settings_source)
        self.assertIn("settings-list-column", settings_source)
        self.assertIn("settings-detail-column", settings_source)
        self.assertNotIn("provider-search", settings_source)
        self.assertNotIn("providerSearch", settings_source)
        self.assertNotIn("filteredProviders", settings_source)
        self.assertNotIn("搜索模型服务", settings_source)
        self.assertNotIn("没有匹配的模型服务", settings_source)
        self.assertIn("providers.map", settings_source)
        self.assertIn("provider-workspace", settings_source)
        self.assertIn(".settings-three-column", styles_source)
        self.assertIn("width: min(100%, 60rem)", styles_source)
        self.assertIn('.settings-workspace .settings-three-column[data-active-section="account"]', styles_source)
        self.assertIn('.settings-workspace .settings-three-column[data-active-section="providers"]', styles_source)
        self.assertIn(".settings-list-column", styles_source)
        self.assertIn(".settings-detail-column", styles_source)
        self.assertNotIn(".provider-search", styles_source)
        self.assertIn(".provider-workspace", styles_source)
        self.assertIn(".settings-workspace", styles_source)
        self.assertIn("官网地址", settings_source)
        self.assertIn("API 地址", settings_source)
        self.assertNotIn("<span>{provider.base_url || provider.default_base_url}</span>", settings_source)
        provider_panel_source = settings_source.split('className="settings-section provider-panel"', 1)[1]
        self.assertLess(provider_panel_source.index("官网地址"), provider_panel_source.index("API 地址"))
        self.assertLess(provider_panel_source.index("API 地址"), provider_panel_source.index("API key"))
        self.assertLess(provider_panel_source.index("API key"), provider_panel_source.index("已添加模型"))
        self.assertNotIn("默认 API 地址", settings_source)
        self.assertNotIn("当前 API 地址", settings_source)
        self.assertNotIn("恢复默认地址", settings_source)
        self.assertNotIn("restoreDefaultBaseUrl", settings_source)
        self.assertNotIn("保存配置", settings_source)
        self.assertNotIn("获取模型列表", settings_source)
        self.assertIn("添加模型", settings_source)
        self.assertIn("autoSaveProviderDraft", settings_source)
        self.assertIn("model-picker-modal", settings_source)
        self.assertIn("selectedProviderModels.map", settings_source)
        self.assertIn("deleteModel", settings_source)

    def test_account_settings_prd_matches_current_four_entry_layout(self):
        prd_source = (self.root / "docs" / "releases" / "v0.1.0" / "prd" / "account-settings.md").read_text(
            encoding="utf-8"
        )
        prd_index_source = (self.root / "docs" / "releases" / "v0.1.0" / "prd" / "README.md").read_text(
            encoding="utf-8"
        )
        acceptance_source = (self.root / "docs" / "releases" / "v0.1.0" / "acceptance.md").read_text(
            encoding="utf-8"
        )
        responsibility_source = (self.root / "docs" / "shared" / "frontend-backend-responsibilities.md").read_text(
            encoding="utf-8"
        )
        v1_vision_source = (self.root / "docs" / "releases" / "v1.0.0-draft" / "vision.md").read_text(
            encoding="utf-8"
        )

        for expected in [
            "- `账号资料` 子模块",
            "- `密码安全` 子模块",
            "- `默认模型` 子模块",
            "1. `账号资料`\n2. `密码安全`\n3. `模型提供方`\n4. `默认模型`",
            "账号资料、密码安全和默认模型在非窄屏下使用设置入口加详情区两列",
            "`max-width: 650px` 时采用手机设置式逐级推进",
            "| 账号资料自动保存中 |",
        ]:
            self.assertIn(expected, prd_source)

        self.assertNotIn("账号设置页内部导航包含 `账号信息` 和 `模型服务`。", acceptance_source)
        self.assertIn("账号设置页内部导航包含 `账号资料`、`密码安全`、`模型提供方` 和 `默认模型`。", acceptance_source)
        self.assertIn("`账号资料` 展示当前 `account` 和 `user_name`。", acceptance_source)
        self.assertIn("账号资料、密码安全、模型提供方、默认模型", prd_index_source)
        self.assertNotIn("账号信息、修改密码、模型服务", prd_index_source)
        self.assertIn("保存账号资料、模型服务配置和默认模型用途", responsibility_source)
        self.assertNotIn("保存账号信息、模型服务配置", responsibility_source)
        self.assertIn("`账号资料`、`密码安全`、`模型提供方` 和 `默认模型`", v1_vision_source)
        self.assertNotIn("`账号信息` 和 `模型服务` 两个入口", v1_vision_source)

    def test_settings_account_items_live_in_primary_column(self):
        settings_source = self.source("frontend/src/features/settings/SettingsShell.tsx")

        primary_nav_marker = 'className="settings-nav settings-primary-nav"'
        list_column_marker = 'className="settings-list-column"'
        detail_column_marker = '<main className="settings-detail-column"'
        self.assertIn(primary_nav_marker, settings_source)
        self.assertIn(list_column_marker, settings_source)
        self.assertIn(detail_column_marker, settings_source)

        primary_nav_source = settings_source.split(primary_nav_marker, 1)[1].split(list_column_marker, 1)[0]
        provider_list_source = settings_source.split(list_column_marker, 1)[1].split(detail_column_marker, 1)[0]

        self.assertIn("settings-root-list", primary_nav_source)
        self.assertIn("账号资料", primary_nav_source)
        self.assertIn("密码安全", primary_nav_source)
        self.assertIn("模型提供方", primary_nav_source)
        self.assertIn("默认模型", primary_nav_source)
        self.assertNotIn("settings-account-subnav", primary_nav_source)
        self.assertNotIn("账号信息", settings_source)
        self.assertNotIn("保存账号资料", settings_source)
        self.assertNotIn("function saveAccount", settings_source)
        self.assertNotIn("onSubmit={saveAccount}", settings_source)
        self.assertIn("function autoSaveAccountName", settings_source)
        self.assertIn("window.setTimeout(() => {", settings_source)
        self.assertIn("void autoSaveAccountName(trimmedName);", settings_source)
        self.assertNotIn("账号资料", provider_list_source)
        self.assertNotIn("密码安全", provider_list_source)
        self.assertIn("providers.map", provider_list_source)

    def test_settings_profile_fields_are_wide_and_neutral(self):
        styles_source = self.source("frontend/src/styles.css")
        settings_source = self.source("frontend/src/styles/settings.css")
        favorites_source = self.source("frontend/src/styles/favorites.css")

        settings_section_source = styles_source.split(
            ".settings-workspace .settings-section {",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("max-width: 760px;", settings_section_source)
        self.assertNotIn("max-width: 640px;", settings_section_source)

        profile_grid_source = styles_source.split(
            ".settings-workspace .account-profile-grid {",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("width: min(100%, 760px);", profile_grid_source)
        self.assertIn("max-width: none;", profile_grid_source)
        self.assertNotIn("max-width: 520px;", profile_grid_source)

        for warm_ordinary_surface in [
            "oklch(99% 0.006 103)",
            "oklch(98.3% 0.01 112)",
            "oklch(96.8% 0.012 108)",
            "oklch(96.4% 0.013 110)",
        ]:
            self.assertNotIn(warm_ordinary_surface, settings_source)
            self.assertNotIn(warm_ordinary_surface, favorites_source)

    def test_settings_mobile_drilldown_state_is_explicit(self):
        settings_source = self.source("frontend/src/features/settings/SettingsShell.tsx")
        settings_view_source = self.source("frontend/src/features/settings/SettingsView.tsx")
        settings_types_source = self.source("frontend/src/features/settings/settingsTypes.ts")

        self.assertIn("type SettingsMobileLayer =", settings_types_source)
        for layer in ['"root"', '"provider-list"', '"account-profile"', '"account-password"', '"provider-detail"']:
            self.assertIn(layer, settings_types_source)
        self.assertNotIn('"account-list"', settings_types_source)
        self.assertIn('const [mobileLayer, setMobileLayer] = useState<SettingsMobileLayer>("root");', settings_source)
        self.assertIn("function settingsMobileLayerTitle()", settings_source)
        self.assertIn("function goBackSettingsLayer()", settings_source)
        self.assertIn("mobileSidebarToggle?: ReactNode", settings_source)
        self.assertIn("mobileSidebarToggle ??", settings_view_source)
        self.assertIn("data-active-section={activeSection}", settings_view_source)
        self.assertIn("data-mobile-layer={mobileLayer}", settings_view_source)
        self.assertIn('className="settings-mobile-layer-header"', settings_view_source)
        self.assertIn('aria-label="返回上一级"', settings_view_source)
        self.assertIn("<SidebarBackIcon />", settings_view_source)
        self.assertNotIn("‹", settings_view_source)
        self.assertNotIn('setMobileLayer("account-list")', settings_source)
        self.assertIn('setMobileLayer("provider-list")', settings_source)
        self.assertIn('setMobileLayer(panel === "profile" ? "account-profile" : "account-password")', settings_source)
        self.assertIn('setMobileLayer("provider-detail")', settings_source)

    def test_settings_responsive_columns_follow_confirmed_breakpoints(self):
        styles_source = self.source("frontend/src/styles.css")

        account_desktop_marker = '.settings-workspace .settings-three-column[data-active-section="account"] {'
        provider_desktop_marker = '.settings-workspace .settings-three-column[data-active-section="providers"] {'
        tablet_media_marker = '@media (min-width: 651px) and (max-width: 1000px)'
        account_profile_grid_marker = ".settings-workspace .account-profile-grid {"
        password_grid_marker = ".settings-workspace .password-grid {"
        mobile_media_marker = "@media (max-width: 650px)"

        self.assertIn(account_desktop_marker, styles_source)
        self.assertIn(provider_desktop_marker, styles_source)
        self.assertIn(tablet_media_marker, styles_source)
        self.assertIn(account_profile_grid_marker, styles_source)
        self.assertIn(password_grid_marker, styles_source)
        self.assertIn(mobile_media_marker, styles_source)

        account_desktop_source = styles_source.split(account_desktop_marker, 1)[1].split("}", 1)[0]
        provider_desktop_source = styles_source.split(provider_desktop_marker, 1)[1].split("}", 1)[0]
        tablet_media_source = styles_source.split(tablet_media_marker, 1)[1].split("@media ", 1)[0]
        self.assertIn(account_desktop_marker, tablet_media_source)
        tablet_account_source = tablet_media_source.split(account_desktop_marker, 1)[1].split("}", 1)[0]
        tablet_provider_source = tablet_media_source.split(provider_desktop_marker, 1)[1].split("}", 1)[0]
        account_profile_grid_source = styles_source.split(account_profile_grid_marker, 1)[1].split("}", 1)[0]
        password_grid_source = styles_source.split(password_grid_marker, 1)[1].split("}", 1)[0]
        mobile_media_source = styles_source.rsplit(
            '@media (max-width: 650px) {\n  .patient-main:has(.favorites-workspace)',
            1,
        )[1].split("@keyframes ", 1)[0]

        self.assertIn("grid-template-columns: minmax(136px, 170px) minmax(0, 1fr);", account_desktop_source)
        self.assertIn(
            "grid-template-columns: minmax(136px, 170px) 220px minmax(0, 1fr);",
            provider_desktop_source,
        )
        self.assertIn("minmax(136px, 170px)", account_desktop_source)
        self.assertIn("minmax(136px, 170px)", provider_desktop_source)
        self.assertIn("grid-template-columns: 160px minmax(0, 1fr);", tablet_account_source)
        self.assertIn("grid-template-columns: 160px 220px minmax(0, 1fr);", tablet_provider_source)
        self.assertNotIn("grid-template-columns: 136px 220px minmax(0, 1fr);", tablet_provider_source)
        self.assertNotIn("minmax(154px, 0.25fr)", tablet_account_source)
        self.assertNotIn("minmax(154px, 0.25fr)", tablet_provider_source)
        self.assertNotIn("minmax(210px, 0.33fr)", tablet_provider_source)
        self.assertNotIn("170px", tablet_provider_source)
        self.assertNotIn("184px", tablet_provider_source)
        self.assertNotIn("250px", tablet_provider_source)
        self.assertNotIn("300px", tablet_provider_source)
        self.assertIn(".favorites-workspace .favorite-layout {", tablet_media_source)
        self.assertIn(
            "grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);",
            tablet_media_source,
        )
        self.assertIn(".settings-mobile-layer-header", styles_source)
        self.assertIn('.settings-three-column[data-mobile-layer="root"] .settings-primary-nav', styles_source)
        self.assertNotIn('.settings-three-column[data-mobile-layer="account-list"] .settings-primary-nav', styles_source)
        self.assertIn('.settings-three-column[data-mobile-layer="provider-list"] .settings-list-column', styles_source)
        self.assertIn('.settings-three-column[data-mobile-layer="account-profile"] .settings-detail-column', styles_source)
        self.assertIn('.settings-three-column[data-mobile-layer="account-password"] .settings-detail-column', styles_source)
        self.assertIn('.settings-three-column[data-mobile-layer="provider-detail"] .settings-detail-column', styles_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", account_profile_grid_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", password_grid_source)
        self.assertIn(".default-model-trigger", styles_source)
        default_model_trigger_source = styles_source.split(".settings-workspace .default-model-trigger {", 1)[1].split(
            "}",
            1,
        )[0]
        self.assertIn("width: 100%;", default_model_trigger_source)
        self.assertIn("display: flex;", default_model_trigger_source)
        self.assertIn(".settings-workspace,", mobile_media_source)
        self.assertIn("grid-template-rows: minmax(0, 1fr);", mobile_media_source)
        self.assertIn(".settings-workspace .settings-toolbar {\n    display: none;", mobile_media_source)
        self.assertIn("width: 100%;", mobile_media_source)
        self.assertIn("overflow-x: hidden;", mobile_media_source)
        self.assertIn('.settings-workspace .settings-three-column[data-active-section="account"]', mobile_media_source)
        self.assertIn('.settings-workspace .settings-three-column[data-active-section="providers"]', mobile_media_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", mobile_media_source)
        self.assertIn("grid-column: 1 / -1;", mobile_media_source)
        self.assertIn(".settings-workspace .provider-row {", mobile_media_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto;", mobile_media_source)

        settings_source = self.source("frontend/src/features/settings/SettingsShell.tsx")
        provider_list_source = settings_source.split('className="provider-list"', 1)[1].split(
            "{!providers.length",
            1,
        )[0]
        self.assertIn("const connectionState = providerConnectionStates[provider.provider_id]", provider_list_source)
        self.assertIn('aria-label={`测试连接：${provider.provider_name}`}', provider_list_source)
        self.assertIn('className={`status provider-configured-icon provider-list-test-icon ${connectionState.status}`}', provider_list_source)
        self.assertIn("data-tooltip={connectionState.message || \"测试连接\"}", provider_list_source)
        self.assertIn("{renderProviderTestIcon(connectionState.status)}", provider_list_source)
        self.assertIn('className="settings-nav-chevron provider-row-chevron"', provider_list_source)
        self.assertIn('disabled={connectionState.status === "testing"}', provider_list_source)
        self.assertNotIn("provider.configured ? (", provider_list_source)
        self.assertNotIn("provider.default ? (", provider_list_source)
        self.assertNotIn("provider-default-icon", provider_list_source)
        self.assertNotIn('aria-label="默认模型服务"', provider_list_source)
        self.assertNotIn("StarIcon", provider_list_source)
        self.assertNotIn('{provider.configured ? "已配置" : "未配置"}', provider_list_source)
        self.assertNotIn(">已配置<", provider_list_source)
        self.assertNotIn("未配置", provider_list_source)

        configured_icon_source = styles_source.split(".settings-workspace .provider-configured-icon {", 1)[1].split(
            "}",
            1,
        )[0]
        self.assertIn("width: 16px;", configured_icon_source)
        self.assertIn("border: 0;", configured_icon_source)
        self.assertIn("background: transparent;", configured_icon_source)
        self.assertIn("color: var(--success);", configured_icon_source)
        self.assertNotIn("provider-default-icon", styles_source)
        self.assertIn(".settings-workspace .provider-list-test-icon.success", styles_source)

    def test_settings_page_api_key_input_is_visible(self):
        settings_source = self.source("frontend/src/features/settings/SettingsShell.tsx")
        types_source = (self.root / "frontend" / "src" / "api" / "types.ts").read_text(
            encoding="utf-8"
        )
        api_source = (
            self.root / "frontend" / "src" / "api" / "modelProviderApi.ts"
        ).read_text(encoding="utf-8")

        self.assertRegex(settings_source, r"(?s)API key.*<SecretInput")
        self.assertIn('labelForAction="API key"', settings_source)
        self.assertIn("api_key?: string", types_source)
        self.assertIn("official_url?: string", types_source)
        self.assertIn("apiKey: provider.api_key", settings_source)
        self.assertIn("officialUrl: provider.official_url", settings_source)
        self.assertIn("api_key: apiKey", api_source)
        self.assertIn("official_url: officialUrl", api_source)
        self.assertIn("function deleteModel", api_source)
        self.assertIn("encodeURIComponent(modelId)", api_source)
        self.assertIn("model.supports_text", api_source)
        self.assertNotIn("supports_vision", api_source)
        self.assertNotIn("supports_vision", types_source)
        self.assertIn("thinking_modes: model.thinking_modes", api_source)
        self.assertNotIn("supports_file_input", types_source)
        self.assertNotIn("supports_file_input", api_source)
        self.assertNotIn("model.capabilities", settings_source)
        self.assertNotIn("capabilities: capabilities", api_source)
        self.assertNotIn("ModelCapabilities", types_source)
        self.assertIn("remoteModels.map", settings_source)
        self.assertNotIn("remoteModels.sort", settings_source)
        self.assertNotIn("重新输入可覆盖保存", settings_source)
        self.assertNotIn("API key 不会明文回显", settings_source)

    def test_account_settings_prd_matches_current_implemented_scope(self):
        account_settings_prd = (
            self.root / "docs" / "releases" / "v0.1.0" / "prd" / "account-settings.md"
        ).read_text(encoding="utf-8")
        account_settings_technical = (
            self.root / "docs" / "releases" / "v0.1.0" / "technical" / "account-settings.md"
        ).read_text(encoding="utf-8")
        acceptance = (self.root / "docs" / "releases" / "v0.1.0" / "acceptance.md").read_text(
            encoding="utf-8"
        )
        settings_shell = self.source("frontend/src/features/settings/SettingsShell.tsx")
        settings_view = self.source("frontend/src/features/settings/SettingsView.tsx")
        model_api = self.source("frontend/src/api/modelProviderApi.ts")

        self.assertIn("- 设置页独立加载中占位", account_settings_prd)
        self.assertIn("- 密码修改提交中的禁用防重复状态", account_settings_prd)
        self.assertNotIn("| 加载中 | 展示设置页加载状态，不展示上一账号残留数据 |", account_settings_prd)
        self.assertNotIn("| 修改密码中 | 禁止重复提交，展示修改中状态 |", account_settings_prd)
        self.assertIn("| 模型提供方加载失败 | 在模型提供方列表展示错误消息 |", account_settings_prd)
        self.assertIn("| 修改密码成功 | 展示成功反馈并清空三个密码输入框 |", account_settings_prd)
        self.assertIn(
            "| `POST /api/model-providers` | 自动保存/新增或更新模型服务配置 |",
            account_settings_technical,
        )
        self.assertNotIn(
            "| `POST /api/model-providers` | 新增模型服务配置 |",
            account_settings_technical,
        )
        self.assertIn(
            "当前前端密码修改没有单独的提交中禁用防重复状态",
            account_settings_technical,
        )
        self.assertIn(
            "模型提供方配置加载失败时在服务列表展示错误消息",
            acceptance,
        )
        self.assertIn(
            "默认模型设置页支持分别维护 `chat`、`title`、`vision_parse` 和 `compact`。",
            acceptance,
        )

        change_password_source = settings_shell.split("async function changePassword", 1)[1].split(
            "async function autoSaveProviderDraft",
            1,
        )[0]
        password_form_source = settings_view.split('className="settings-section password-section"', 1)[1].split(
            "</form>",
            1,
        )[0]
        self.assertIn('setCurrentPassword("")', change_password_source)
        self.assertIn('setNewPassword("")', change_password_source)
        self.assertIn('setConfirmPassword("")', change_password_source)
        self.assertNotIn('status: "saving"', change_password_source)
        self.assertNotIn("disabled=", password_form_source)
        self.assertIn("setLoadError(error instanceof Error ? error.message : \"模型提供方加载失败\")", settings_shell)
        self.assertIn('{loadError ? <p className="status-message error">{loadError}</p> : null}', settings_view)
        self.assertIn('disabled={connectionState.status === "testing"}', settings_view)
        self.assertIn("scheduleProviderConnectionFeedbackReset", settings_shell)
        self.assertIn("modelPickerLoading ? <p", settings_view)
        self.assertIn("retryLoadRemoteModels", settings_view)
        self.assertIn('"POST"', model_api)
        self.assertIn('"/model-providers"', model_api)
        self.assertIn('<span>默认模型</span>', settings_view)
        self.assertIn('type SettingsSection = "account" | "providers" | "defaults"', self.source("frontend/src/features/settings/settingsTypes.ts"))
        self.assertIn("apiClient.updateModelDefaults({ [usage]: nextModelId || null })", settings_shell)
        for usage in ['key: "chat"', 'key: "title"', 'key: "vision_parse"', 'key: "compact"']:
            self.assertIn(usage, settings_shell)
        for label in ["聊天模型", "标题生成模型", "视觉解析模型", "压缩上下文模型"]:
            self.assertIn(label, settings_shell)
        default_model_usage_source = settings_shell.split("const defaultModelUsages", 1)[1].split(
            "const emptyDefaultModelFeedback",
            1,
        )[0]
        self.assertNotIn("默认聊天模型", default_model_usage_source)
        self.assertNotIn("压缩对话历史模型", default_model_usage_source)
        self.assertNotIn("description", default_model_usage_source)
        self.assertIn('aria-label={`设置${item.label}`}', settings_view)
        self.assertIn("defaultModelItems.map", settings_view)
        self.assertIn("function defaultModelOptionsForUsage(usage: DefaultModelUsage)", settings_view)
        self.assertIn('if (usage !== "vision_parse")', settings_view)
        self.assertIn('mimeType.startsWith("image/")', settings_view)
        self.assertIn("defaultModelOptionsForUsage(item.key).map", settings_view)
        default_model_section = settings_view.split('className="settings-section default-model-section"', 1)[1].split(
            '</section>',
            1,
        )[0]
        self.assertNotIn("<select", default_model_section)
        self.assertNotIn("item.description", default_model_section)
        self.assertNotIn("首页对话", default_model_section)
        self.assertNotIn("会话标题", default_model_section)
        self.assertNotIn("预留入口", default_model_section)
        self.assertIn('className="default-model-picker"', default_model_section)
        self.assertIn('className="default-model-trigger"', default_model_section)
        self.assertIn('className="default-model-popover"', default_model_section)
        self.assertIn('"default-model-option"', default_model_section)
        self.assertIn("openDefaultModelPicker", settings_view)
        self.assertIn("currentDefaultModelName(item)", settings_view)
        self.assertIn("updateDefaultModel", settings_shell)
        self.assertNotIn("defaultModelFeedback", settings_shell)
        self.assertNotIn("default-model-feedback", default_model_section)
        self.assertNotIn("item.feedback", default_model_section)
        update_default_model_source = settings_shell.split("async function updateDefaultModel", 1)[1].split(
            "async function deleteAddedModel",
            1,
        )[0]
        self.assertNotIn("保存中...", update_default_model_source)
        self.assertNotIn("已保存。", update_default_model_source)
        add_model_section = account_settings_technical.split("## 9. 添加和读取模型", 1)[1].split(
            "## 10. 默认模型用途设置",
            1,
        )[0]
        self.assertNotIn('"default": true', add_model_section)
        self.assertNotIn('"default": false', add_model_section)

    def test_default_model_picker_uses_home_model_control_visual_language(self):
        styles_source = self.source("frontend/src/styles.css")

        self.assertNotIn(".settings-workspace .default-model-row select", styles_source)
        default_model_section_styles = styles_source.split(
            ".settings-workspace .default-model-section {",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("width: min(100%, 920px);", default_model_section_styles)

        default_model_list_styles = styles_source.split(
            ".settings-workspace .default-model-list {",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("gap: 0;", default_model_list_styles)

        default_model_row_styles = styles_source.split(
            ".settings-workspace .default-model-row {",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("grid-template-columns: minmax(136px, 180px) minmax(320px, 1fr);", default_model_row_styles)
        self.assertNotIn(".settings-workspace .default-model-feedback", styles_source)

        default_model_picker_styles = styles_source.split(
            ".settings-workspace .default-model-picker {",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("position: relative;", default_model_picker_styles)
        self.assertIn("width: 100%;", default_model_picker_styles)

        default_model_trigger_styles = styles_source.split(
            ".settings-workspace .default-model-trigger {",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("width: 100%;", default_model_trigger_styles)
        self.assertIn("min-height: 38px;", default_model_trigger_styles)
        self.assertIn("background: oklch(96.3% 0.014 284);", default_model_trigger_styles)

        default_model_popover_styles = styles_source.split(
            ".settings-workspace .default-model-popover {",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("position: absolute;", default_model_popover_styles)
        self.assertIn("width: 100%;", default_model_popover_styles)
        self.assertIn("max-height: min(320px, calc(100vh - 220px));", default_model_popover_styles)

        default_model_option_styles = styles_source.split(
            ".settings-workspace .default-model-option {",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("min-height: 36px;", default_model_option_styles)
        self.assertIn("text-align: left;", default_model_option_styles)
        self.assertIn(".settings-workspace .default-model-option.active", styles_source)

    def test_settings_page_uses_column_scrollers_and_visual_model_actions(self):
        settings_source = self.source("frontend/src/features/settings/SettingsShell.tsx")
        settings_workspace_source = self.source("frontend/src/features/settings/SettingsWorkspacePanel.tsx")
        app_source = self.source("frontend/src/App.tsx")
        icons_source = self.source("frontend/src/components/icons.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertNotIn("管理账号与模型配置", app_source)
        self.assertIn("SettingsWorkspacePanel", app_source)
        self.assertIn('className="settings-toolbar"', settings_workspace_source)
        self.assertIn('workspaceShell.renderSidebarToggle("settings-sidebar-toggle")', app_source)
        self.assertIn("mobileSidebarToggle={settingsSidebarToggle}", settings_workspace_source)
        self.assertNotIn('aria-label="关闭账号设置"', app_source)

        self.assertIn("function PlusIcon", settings_source)
        self.assertIn("function XIcon", icons_source)
        self.assertIn("function LightningIcon", icons_source)
        self.assertIn("function CheckIcon", icons_source)
        self.assertIn("function TrashIcon", icons_source)
        self.assertIn('aria-label="添加模型"', settings_source)
        self.assertIn('aria-label="关闭添加模型"', settings_source)
        self.assertIn('className="secondary-button settings-icon-button add-model-button"', settings_source)
        self.assertIn('className="secondary-button settings-icon-button"', settings_source)
        self.assertIn("selectedProviderFeedback", settings_source)
        self.assertIn('className={`status-message provider-feedback ${selectedProviderFeedback.status}`}', settings_source)
        self.assertIn("modelPickerError", settings_source)
        self.assertIn('className="model-picker-error-actions"', settings_source)
        self.assertIn("retryLoadRemoteModels", settings_source)

        provider_list_source = settings_source.split('className="provider-list"', 1)[1].split(
            "{!providers.length",
            1,
        )[0]
        self.assertNotIn("已配置", provider_list_source)
        self.assertNotIn("未配置", provider_list_source)
        self.assertNotIn("个模型", provider_list_source)
        self.assertIn("connectionState.message || \"测试连接\"", provider_list_source)
        self.assertIn('className={`status provider-configured-icon provider-list-test-icon ${connectionState.status}`}', provider_list_source)
        self.assertIn('disabled={connectionState.status === "testing"}', provider_list_source)
        self.assertIn("{renderProviderTestIcon(connectionState.status)}", provider_list_source)
        self.assertNotIn("测试中...", provider_list_source)

        model_header_source = settings_source.split('className="model-section-header"', 1)[1].split(
            'className="model-list"',
            1,
        )[0]
        self.assertLess(model_header_source.index("已添加模型"), model_header_source.index("个模型"))
        self.assertIn("<span className=\"status\">{selectedProviderModels.length} 个模型</span>", model_header_source)

        model_actions_source = settings_source.split('className="model-row-actions"', 1)[1].split("</div>", 1)[0]
        self.assertIn('className="settings-icon-button model-delete-button danger"', model_actions_source)
        self.assertIn('aria-label={`删除模型：${model.model_name}`}', model_actions_source)
        self.assertIn('title="删除模型"', model_actions_source)
        self.assertIn('<TrashIcon className="settings-action-icon" />', model_actions_source)
        self.assertNotIn('model-default-button', model_actions_source)
        self.assertNotIn('StarIcon', model_actions_source)
        self.assertNotIn(">设为默认<", model_actions_source)
        self.assertNotIn(">默认模型<", model_actions_source)
        self.assertNotIn(">删除<", model_actions_source)

        settings_workspace_source = styles_source.split("/* Settings surface styles. */", 1)[1].split(".settings-workspace {", 1)[1].split("}", 1)[0]
        settings_shell_source = styles_source.split(".settings-shell {", 1)[1].split("}", 1)[0]
        self.assertIn("display: flex;", settings_workspace_source)
        self.assertIn("flex-direction: column;", settings_workspace_source)
        self.assertIn("height: 100%;", settings_workspace_source)
        self.assertNotIn("max-height:", settings_workspace_source)
        self.assertIn("height: 100%;", settings_shell_source)
        self.assertNotIn("height: min(560px, calc(100vh - 146px));", settings_shell_source)
        self.assertIn("overflow: hidden;", styles_source)
        self.assertRegex(styles_source, r"(?s)\.settings-primary-nav,\n\.settings-list-column,\n\.settings-detail-column \{[^}]*overflow-y: auto;")
        self.assertIn(".settings-icon-button", styles_source)
        self.assertIn(".settings-action-icon", styles_source)
        self.assertIn(".provider-list-test-icon", styles_source)
        self.assertIn(".provider-list-test-icon[data-tooltip]::after", styles_source)
        self.assertIn("@media (max-width: 1000px) {\n  .patient-main:has(.settings-workspace)", styles_source)
        self.assertIn("@media (max-width: 650px)", styles_source)
        settings_main_source = styles_source.split(".patient-main:has(.settings-workspace) {", 1)[1].split("}", 1)[0]
        settings_redesign_source = styles_source.split("/* Serenita redesign: settings workspace. */", 1)[1].split(
            ".settings-workspace {",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("padding: 0;", settings_main_source)
        self.assertIn("padding: 0;", settings_redesign_source)
        self.assertNotIn("padding: 0 22px 20px;", settings_redesign_source)

    def test_settings_visual_language_stays_compact_and_consistent(self):
        settings_source = self.source("frontend/src/features/settings/SettingsShell.tsx")
        styles_source = self.source("frontend/src/styles.css")

        for redundant_copy in [
            "<span>账号设置</span>",
            "<span>远端模型</span>",
            'placeholder="输入 API key"',
            "还没有添加模型。",
            "正在加载远端模型...",
        ]:
            self.assertNotIn(redundant_copy, settings_source)

        provider_list_source = settings_source.split('className="provider-list"', 1)[1].split(
            "{!providers.length",
            1,
        )[0]
        self.assertNotIn("<span>模型服务</span>", provider_list_source)

        shared_title_source = styles_source.split(
            ".settings-workspace .settings-toolbar,\n.settings-workspace .settings-mobile-layer-header {",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("height: var(--workspace-titlebar-height);", shared_title_source)
        self.assertIn("--workspace-titlebar-height: 52px;", styles_source)
        self.assertIn("border-bottom: 1px solid var(--settings-line-soft);", shared_title_source)
        self.assertIn("border-radius: 0;", shared_title_source)

        settings_surface_source = styles_source.split(".settings-workspace .settings-three-column {", 1)[1].split(
            "}",
            1,
        )[0]
        self.assertIn("border: 0;", settings_surface_source)
        self.assertIn("border-radius: 0;", settings_surface_source)
        self.assertIn("background: transparent;", settings_surface_source)
        self.assertIn("box-shadow: none;", settings_surface_source)
        self.assertNotIn("border-top: 0;", settings_surface_source)

        compact_title_source = styles_source.split(".settings-workspace .settings-section h1 {", 1)[1].split("}", 1)[0]
        self.assertIn("font-size: var(--text-section-title);", compact_title_source)
        self.assertIn("--text-section-title: 18px;", styles_source)
        self.assertIn("line-height: 1.24;", compact_title_source)

        compact_controls_source = styles_source.split(".settings-workspace {", 1)[1].split("}", 1)[0]
        self.assertIn("--settings-control-height: 36px;", compact_controls_source)
        self.assertIn("--settings-icon-button-size: 32px;", compact_controls_source)

    def test_provider_connection_test_feedback_stays_on_icon_button(self):
        settings_source = self.source("frontend/src/features/settings/SettingsShell.tsx")
        styles_source = self.source("frontend/src/styles.css")

        provider_form_source = settings_source.split('className="provider-form"', 1)[1].split("</form>", 1)[0]
        self.assertNotIn("connectionState.message", provider_form_source)
        self.assertNotIn('status-message ${connectionState.status}', settings_source)
        self.assertIn('message: result.reachable ? "连接成功" : "连接失败"', settings_source)
        self.assertIn('message: error instanceof Error ? error.message : "连接失败"', settings_source)
        self.assertIn("connectionState.message || \"测试连接\"", settings_source)
        self.assertIn('className={`status provider-configured-icon provider-list-test-icon ${connectionState.status}`}', settings_source)
        self.assertIn('disabled={connectionState.status === "testing"}', settings_source)
        self.assertIn("providerConnectionFeedbackDurationMs = 5000", settings_source)
        self.assertIn("connectionFeedbackTimeoutsRef", settings_source)
        self.assertIn("scheduleProviderConnectionFeedbackReset", settings_source)
        self.assertIn("window.clearTimeout", settings_source)
        self.assertIn("window.setTimeout", settings_source)
        self.assertIn("defaultConnectionTestState", settings_source)
        self.assertIn("return <LightningIcon />;", settings_source)
        self.assertIn("return <CheckIcon />;", settings_source)
        self.assertIn("return <XIcon />;", settings_source)
        self.assertIn("content: attr(data-tooltip);", styles_source)
        self.assertIn(".provider-list-test-icon.success", styles_source)
        self.assertIn(".provider-list-test-icon.error", styles_source)

    def test_secret_input_supports_right_side_reveal_toggle(self):
        secret_input_source = (
            self.root / "frontend" / "src" / "components" / "SecretInput.tsx"
        ).read_text(encoding="utf-8")
        icons_source = self.source("frontend/src/components/icons.tsx")
        auth_source = self.source("frontend/src/features/auth/AuthPage.tsx")
        settings_source = self.source("frontend/src/features/settings/SettingsShell.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("function EyeIcon", icons_source)
        self.assertIn("function EyeOffIcon", icons_source)
        self.assertIn("EyeIcon, EyeOffIcon", secret_input_source)
        self.assertIn("setRevealed", secret_input_source)
        self.assertIn('type={revealed ? "text" : "password"}', secret_input_source)
        self.assertIn('className="secret-input"', secret_input_source)
        self.assertIn('className="secret-toggle"', secret_input_source)
        self.assertIn('type="button"', secret_input_source)
        self.assertIn("title={`${toggleText}${labelForAction}`}", secret_input_source)
        self.assertIn("{revealed ? <EyeOffIcon /> : <EyeIcon />}", secret_input_source)
        self.assertNotIn("        {toggleText}\n", secret_input_source)
        self.assertGreaterEqual(auth_source.count("<SecretInput"), 2)
        self.assertGreaterEqual(settings_source.count("<SecretInput"), 4)
        self.assertIn(".secret-input", styles_source)
        self.assertIn(".secret-toggle", styles_source)
        self.assertIn(".secret-toggle .secret-toggle-icon", styles_source)

    def test_secret_input_toggle_does_not_shift_on_hover(self):
        styles_source = self.source("frontend/src/styles.css")

        self.assertRegex(
            styles_source,
            r"(?s)button\.secret-toggle:hover:not\(:disabled\),\n"
            r"button\.secret-toggle:focus-visible \{[^}]*transform: translateY\(-50%\);",
        )

    def test_workspace_exposes_quote_and_delete_session_controls(self):
        app_source = self.source("frontend/src/App.tsx")

        self.assertIn("quotedContext", app_source)
        self.assertIn("quoteSelection", app_source)
        self.assertIn("function updateQuoteSelection", app_source)
        self.assertIn("function addSelectedTextToConversation", app_source)
        self.assertIn("添加到对话", app_source)
        self.assertNotIn("引用所选文本", app_source)
        self.assertIn("删除", app_source)
        self.assertIn("deleteConversation", app_source)

    def test_selected_text_quotes_render_as_preview_chips_with_full_tooltips(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("QUOTE_PREVIEW_LENGTH = 10", app_source)
        self.assertIn("function quotePreviewText", app_source)
        self.assertIn("function quoteResourcesFromMessage", app_source)
        self.assertIn("function renderQuoteContextChip", app_source)
        self.assertIn("function renderMessageQuoteReference", app_source)
        self.assertIn("quote-context-chip", app_source)
        self.assertIn("message-quote-reference", app_source)
        self.assertIn("quote-context-tooltip", app_source)
        self.assertIn("aria-label={`引用全文：${quoteText}`}", app_source)
        self.assertIn("quotePreviewText(quotedContext.quote_text)", app_source)
        self.assertIn("renderMessageQuoteReference(quote)", app_source)
        composer_source = app_source.split('className="assistant-composer conversation-composer"', 1)[1].split(
            'className="composer-footer"',
            1,
        )[0]
        self.assertLess(
            composer_source.index("{quotedContext ? ("),
            composer_source.index('className="composer-input-frame"'),
        )
        message_bubble_source = self.message_bubble_source()
        message_display_source = message_bubble_source.split("{isEditingMessage ? (", 1)[1].split(
            "</div>\n      {!isEditingMessage ?",
            1,
        )[0]
        self.assertLess(
            message_display_source.index("{quoteResources.length ? ("),
            message_display_source.index("{hasVisibleMessageBody ? ("),
        )
        self.assertNotIn("renderQuoteContextChip(quote, false)", message_display_source)
        self.assertNotIn("已附加 {message.context_resources.length} 个上下文资源", app_source)
        self.assertNotIn("引用：{quotedContext.preview}", app_source)
        self.assertIn(".quote-context-chip", styles_source)
        self.assertIn(".message-quote-reference", styles_source)
        self.assertIn(".quote-context-tooltip", styles_source)
        message_context_source = styles_source.split(".message-context-list {\n", 1)[1].split("}", 1)[0]
        message_reference_source = styles_source.split(".message-quote-reference {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: 4px;", message_context_source)
        self.assertIn("padding: 0 0 3px;", message_reference_source)
        self.assertNotIn("margin-bottom: 9px;", message_context_source)
        self.assertNotIn("padding: 0 0 7px;", message_reference_source)
        self.assertIn(".quote-context-chip:hover .quote-context-tooltip", styles_source)
        self.assertIn(".quote-context-chip:focus-visible .quote-context-tooltip", styles_source)
        self.assertIn(".message-quote-reference:hover .quote-context-tooltip", styles_source)
        self.assertIn(".message-quote-reference:focus-visible .quote-context-tooltip", styles_source)

    def test_sent_file_context_resources_render_in_user_message_bubbles(self):
        app_source = self.source("frontend/src/App.tsx")
        types_source = self.source("frontend/src/api/types.ts")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("context_resources?: Array<Record<string, unknown>>;", types_source)
        self.assertIn("function fileResourcesFromMessage", app_source)
        self.assertIn("function fileResourcesFromContextResources", app_source)
        self.assertIn("function renderMessageFileReference", app_source)
        self.assertIn("const fileResources = fileResourcesFromContextResources(visibleContextResources, message.message_id)", app_source)
        self.assertIn("response.context_resources ?? input.contextResources", app_source)
        message_bubble_source = self.message_bubble_source()
        message_display_source = message_bubble_source.split("{isEditingMessage ? (", 1)[1].split(
            "</div>\n      {!isEditingMessage ?",
            1,
        )[0]
        self.assertLess(
            message_display_source.index("{fileResources.length || quoteResources.length ? ("),
            message_display_source.index("{hasVisibleMessageBody ? ("),
        )
        self.assertIn("fileResources.map((resource) => renderMessageFileReference(resource))", message_display_source)
        self.assertIn('aria-label={`附件：${resource.name}`}', app_source)
        self.assertIn('className="message-file-reference"', app_source)
        self.assertIn(".message-file-reference", styles_source)

    def test_recent_sessions_expose_row_level_delete_controls(self):
        app_source = self.source("frontend/src/App.tsx")
        icons_source = self.source("frontend/src/components/icons.tsx")
        sidebar_source = self.source("frontend/src/app/Sidebar.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("deleteConversationFromSidebar", app_source)
        self.assertIn("function TrashIcon", icons_source)
        self.assertIn('className="conversation-item-row"', sidebar_source)
        self.assertIn('"conversation-item-frame active" : "conversation-item-frame"', sidebar_source)
        self.assertIn('className="conversation-title-button"', sidebar_source)
        self.assertIn('className="conversation-delete-button"', sidebar_source)
        self.assertIn("<TrashIcon />", sidebar_source)
        self.assertIn('title="删除会话"', sidebar_source)
        self.assertIn('aria-label="会话列表"', sidebar_source)
        self.assertNotIn('aria-label="最近会话"', sidebar_source)
        self.assertNotIn("<h2>最近会话</h2>", sidebar_source)
        self.assertNotIn("<h2>最近对话</h2>", sidebar_source)
        conversation_list_source = sidebar_source.split('className="conversation-list"', 1)[1].split(
            'className="sidebar-bottom"',
            1,
        )[0]
        self.assertNotRegex(conversation_list_source, r">\s*删除\s*</button>")
        self.assertNotIn('onClick={() => void deleteCurrentConversation()}', sidebar_source)
        self.assertIn(".conversation-item-row", styles_source)
        self.assertIn(".conversation-item-frame", styles_source)
        self.assertIn(".conversation-title-button", styles_source)
        self.assertIn(".conversation-delete-button", styles_source)
        self.assertIn(".conversation-item-frame {\n  position: relative;", styles_source)
        self.assertIn(".conversation-title-button {\n  position: relative;", styles_source)
        self.assertIn("border-radius: var(--radius-control);", styles_source)
        self.assertIn("padding: 0 52px 0 14px;", styles_source)
        self.assertIn("position: absolute", styles_source)
        self.assertIn("overflow: hidden", styles_source)
        self.assertIn("z-index: 1", styles_source)
        self.assertIn(".conversation-item-row:hover .conversation-delete-button", styles_source)
        self.assertIn("button.conversation-delete-button:hover:not(:disabled)", styles_source)
        self.assertIn("transform: translateY(-50%);", styles_source)
        self.assertIn(".conversation-list {\n  min-width: 0;", styles_source)
        self.assertIn(".conversation-item-frame {\n  position: relative;", styles_source)
        self.assertIn("min-width: 0;", styles_source)
        self.assertIn("max-width: 100%;", styles_source)
        self.assertIn("text-overflow: ellipsis;", styles_source)

    def test_sidebar_places_health_and_favorites_above_account_at_sidebar_bottom(self):
        icons_source = self.source("frontend/src/components/icons.tsx")
        sidebar_source = self.source("frontend/src/app/Sidebar.tsx")
        styles_source = self.source("frontend/src/styles.css")

        global_nav_source = sidebar_source.split('className="global-nav"', 1)[1].split(
            'className="conversation-list"', 1
        )[0]
        conversation_list_index = sidebar_source.index('className="conversation-list"')
        secondary_nav_index = sidebar_source.index('className="secondary-nav"')
        user_summary_index = sidebar_source.index('className="user-summary"')
        secondary_nav_source = sidebar_source.split('className="secondary-nav"', 1)[1].split(
            'className="user-summary"', 1
        )[0]
        account_button_source = sidebar_source.split('className={route === SETTING_PATH ? "account-button active" : "account-button"}', 1)[1].split(
            "</button>",
            1,
        )[0]

        self.assertIn("开启新对话", global_nav_source)
        self.assertIn("function PlusIcon", icons_source)
        self.assertIn("<PlusIcon />", global_nav_source)
        self.assertNotIn("原始文件", global_nav_source)
        self.assertNotIn("我的收藏", global_nav_source)
        self.assertLess(conversation_list_index, secondary_nav_index)
        self.assertLess(secondary_nav_index, user_summary_index)
        self.assertLess(secondary_nav_source.index("原始文件"), secondary_nav_source.index("我的收藏"))
        self.assertIn("function HealthRecordIcon", icons_source)
        self.assertIn("function FavoriteNavIcon", icons_source)
        self.assertIn("<HealthRecordIcon />", secondary_nav_source)
        self.assertIn("<FavoriteNavIcon />", secondary_nav_source)
        self.assertNotIn("账号设置", global_nav_source)
        self.assertIn('aria-label="账号设置"', sidebar_source)
        self.assertIn("onClick={() => onNavigate(SETTING_PATH)}", account_button_source)
        self.assertIn('className="secondary-nav"', sidebar_source)
        self.assertIn('className="sidebar-bottom"', sidebar_source)
        self.assertIn(".sidebar-bottom {\n  margin-top: auto;", styles_source)
        self.assertIn(".secondary-nav", styles_source)
        self.assertIn(".nav-icon", styles_source)
        self.assertNotIn('.patient-sidebar[data-collapsed="true"] .nav-icon', styles_source)
        self.assertNotIn('content: "+";', styles_source)
        self.assertNotIn('content: "档";', styles_source)
        self.assertNotIn('content: "藏";', styles_source)

    def test_sidebar_supports_desktop_collapse_and_mobile_drawer_without_icon_rail(self):
        app_source = self.source("frontend/src/App.tsx")
        hook_source = self.source("frontend/src/app/useResponsiveSidebar.ts")
        shell_source = self.source("frontend/src/app/PatientShell.tsx")
        sidebar_source = self.source("frontend/src/app/Sidebar.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertNotIn("sidebarHidden", app_source)
        self.assertNotIn("setSidebarHidden", app_source)
        self.assertNotIn('data-sidebar-hidden', app_source)
        self.assertNotIn("grid-template-columns: 76px minmax(0, 1fr);", styles_source)
        self.assertNotIn('.patient-sidebar[data-collapsed="true"]', styles_source)
        self.assertNotIn("76px", styles_source)
        self.assertIn("sidebarCollapsed", app_source)
        self.assertIn("setSidebarCollapsed", hook_source)
        self.assertIn("compactSidebarMode", app_source)
        self.assertIn("function toggleSidebarFromMain", hook_source)
        self.assertIn("function collapseSidebarFromSidebar", hook_source)
        self.assertIn("setSidebarCollapsed(false)", hook_source)
        self.assertIn("setSidebarCollapsed(true)", hook_source)
        self.assertIn('data-sidebar-collapsed={sidebarCollapsed ? "true" : "false"}', shell_source)
        self.assertIn("mobileSidebarOpen", app_source)
        self.assertIn("setMobileSidebarOpen", hook_source)
        self.assertIn('aria-label={sidebarToggleLabel}', app_source)
        self.assertIn('"sidebar-toggle-button"', app_source)
        self.assertIn('className="sidebar-collapse-button"', sidebar_source)
        self.assertIn('className="mobile-sidebar-backdrop"', shell_source)
        self.assertIn('data-mobile-sidebar-open={mobileSidebarOpen ? "true" : "false"}', shell_source)
        self.assertIn(".sidebar-toggle-button", styles_source)
        self.assertIn(".sidebar-collapse-button", styles_source)
        self.assertIn(".mobile-sidebar-backdrop", styles_source)
        self.assertIn('@media (min-width: 1001px)', styles_source)
        self.assertIn('.patient-shell[data-sidebar-collapsed="true"]', styles_source)
        self.assertIn("grid-template-columns: 0 minmax(0, 1fr);", styles_source)
        self.assertIn('.patient-shell[data-sidebar-collapsed="true"] .patient-sidebar', styles_source)
        self.assertIn('SIDEBAR_COMPACT_MEDIA = "(max-width: 1000px)"', hook_source)
        self.assertIn('@media (max-width: 1000px)', styles_source)
        self.assertNotIn('@media (max-width: 860px)', styles_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", styles_source)
        self.assertIn("transform: translateX(-100%);", styles_source)
        self.assertIn('.patient-shell[data-mobile-sidebar-open="true"] .patient-sidebar', styles_source)
        final_shell_source = styles_source.rsplit(".patient-shell {\n  --sidebar-width: 250px;", 1)[1].split("}", 1)[0]
        self.assertIn("grid-template-columns: var(--sidebar-width) minmax(0, 1fr);", final_shell_source)
        self.assertIn("height: 100vh;", final_shell_source)
        self.assertIn("min-height: 100vh;", final_shell_source)
        self.assertIn("overflow: hidden;", final_shell_source)
        self.assertIn(".patient-sidebar {\n  border-right: 1px solid var(--line);", styles_source)
        final_sidebar_source = styles_source.rsplit(".patient-sidebar {\n  border-right: 1px solid var(--line);", 1)[1].split("}", 1)[0]
        self.assertIn("grid-column: 1;", final_sidebar_source)
        self.assertIn("display: flex;", final_sidebar_source)
        self.assertIn("flex-direction: column;", final_sidebar_source)
        final_main_source = styles_source.rsplit(".patient-main {\n  border: 0;", 1)[1].split("}", 1)[0]
        self.assertIn("grid-column: 2;", final_main_source)
        self.assertIn("min-height: 0;", final_main_source)
        self.assertIn("overflow: hidden;", final_main_source)
        self.assertIn(".patient-main:has(.home-workspace) {\n  padding: 0;", styles_source)
        self.assertIn("box-shadow: none;", styles_source)

    def test_sidebar_uses_drawer_before_chat_column_starts_shrinking(self):
        app_source = self.source("frontend/src/App.tsx")
        hook_source = self.source("frontend/src/app/useResponsiveSidebar.ts")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn('SIDEBAR_COMPACT_MEDIA = "(max-width: 1000px)"', hook_source)
        self.assertNotIn("SIDEBAR_AUTO_COLLAPSE_MEDIA", app_source)
        self.assertNotIn("autoSidebarCollapseMode", app_source)
        self.assertNotIn("sidebarAutoCollapsedRef", app_source)
        self.assertIn("const showWorkspaceSidebarToggle = compactSidebarMode ? !mobileSidebarOpen : sidebarCollapsed;", app_source)
        self.assertNotIn("const showWorkspaceSidebarToggle = compactSidebarMode || sidebarCollapsed;", app_source)
        self.assertIn('@media (max-width: 1000px)', styles_source)
        drawer_source = styles_source.split("@media (max-width: 1000px)", 1)[1].split("@media", 1)[0]
        self.assertIn("grid-template-columns: minmax(0, 1fr);", drawer_source)
        self.assertIn("position: fixed;", drawer_source)
        self.assertIn("transform: translateX(-100%);", drawer_source)
        self.assertIn('.patient-shell[data-mobile-sidebar-open="true"] .patient-sidebar', drawer_source)
        desktop_collapse_source = styles_source.split("@media (min-width: 1001px)", 1)[1].split("@media", 1)[0]
        self.assertIn('.patient-shell[data-sidebar-collapsed="true"]', desktop_collapse_source)
        self.assertIn('.patient-shell[data-sidebar-collapsed="false"] .patient-main .sidebar-toggle-button', desktop_collapse_source)
        self.assertIn("display: none;", desktop_collapse_source)
        self.assertNotIn("@media (max-width: 980px)", styles_source)
        self.assertIn("@media (max-width: 650px)", styles_source)
        self.assertNotIn("@media (max-width: 420px)", styles_source)
        self.assertNotIn("@media (max-width: 300px)", styles_source)

    def test_workspace_breakpoint_layouts_do_not_animate_structural_widths(self):
        styles_source = self.source("frontend/src/styles.css")

        final_shell_source = styles_source.rsplit(".patient-shell {\n  --sidebar-width: 250px;", 1)[1].split("}", 1)[0]
        final_sidebar_source = styles_source.rsplit(".patient-sidebar {\n  border-right: 1px solid var(--line);", 1)[
            1
        ].split("}", 1)[0]

        self.assertNotIn("transition: grid-template-columns", final_shell_source)
        self.assertNotIn("grid-template-columns var(--transition-fast)", final_shell_source)
        self.assertNotIn("padding-inline var(--transition-fast)", final_sidebar_source)

    def test_favorites_split_widths_stay_fluid_from_651_to_1000(self):
        styles_source = self.source("frontend/src/styles.css")
        tablet_media_marker = '@media (min-width: 651px) and (max-width: 1000px)'
        tablet_media_source = styles_source.split(tablet_media_marker, 1)[1].split("@media ", 1)[0]
        tablet_favorites_source = tablet_media_source.split(".favorites-workspace .favorite-layout {", 1)[1].split(
            "}",
            1,
        )[0]

        self.assertIn("grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);", tablet_favorites_source)
        self.assertNotIn("minmax(280px, 0.95fr)", tablet_favorites_source)
        self.assertNotIn("minmax(320px, 1.05fr)", tablet_favorites_source)

    def test_sidebar_bottom_nav_stays_vertical_on_narrow_widths_and_mobile_close_uses_x_icon(self):
        sidebar_source = self.source("frontend/src/app/Sidebar.tsx")
        styles_source = self.source("frontend/src/styles.css")

        mobile_close_source = sidebar_source.split('className="mobile-sidebar-close-button"', 1)[1].split(
            "</button>",
            1,
        )[0]
        sidebar_collapse_source = sidebar_source.split('className="sidebar-collapse-button"', 1)[1].split(
            "</button>",
            1,
        )[0]
        secondary_nav_source = styles_source.rsplit(".secondary-nav {\n  display: grid;", 1)[1].split("}", 1)[0]

        self.assertIn("<SidebarCloseIcon />", mobile_close_source)
        self.assertIn("<SidebarCloseIcon />", sidebar_collapse_source)
        self.assertNotIn("<SidebarToggleIcon", mobile_close_source)
        self.assertNotIn("<SidebarToggleIcon", sidebar_collapse_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", secondary_nav_source)

    def test_workspace_title_uses_token_sized_bold_type_without_responsive_shrink(self):
        styles_source = self.source("frontend/src/styles.css")

        title_blocks = [
            block.split("}", 1)[0]
            for block in styles_source.split(".workspace-titlebar h1 {")[1:]
        ]
        final_title_source = title_blocks[-1]
        narrow_drawer_source = styles_source.split("@media (max-width: 1000px)", 1)[1].split(
            "@media",
            1,
        )[0]

        self.assertIn("font-size: var(--text-title);", final_title_source)
        self.assertIn("font-weight: 760;", final_title_source)
        self.assertIn("overflow: hidden;", final_title_source)
        self.assertNotRegex("\n".join(title_blocks), r"font-size:\s*\\d+px;")
        self.assertNotIn(".workspace-titlebar h1", narrow_drawer_source)

    def test_shell_supports_phone_width_without_tiny_breakpoints(self):
        styles_source = self.source("frontend/src/styles.css")

        body_source = styles_source.split("body {\n", 1)[1].split("}", 1)[0]
        model_name_source = styles_source.split(".composer-model-name {", 1)[1].split("}", 1)[0]

        self.assertIn("min-width: 300px;", body_source)
        self.assertNotIn("min-width: 420px;", body_source)
        self.assertNotIn("min-width: 200px;", body_source)
        self.assertNotIn("min-width: 320px;", body_source)
        self.assertNotIn("min-width: 360px;", body_source)
        self.assertNotIn("@media (max-width: 420px)", styles_source)
        self.assertNotIn("@media (max-width: 360px)", styles_source)
        self.assertNotIn("@media (max-width: 300px)", styles_source)
        self.assertIn("min-width: 0;", model_name_source)
        self.assertIn("overflow: hidden;", model_name_source)
        self.assertIn("text-overflow: ellipsis;", model_name_source)
        self.assertIn("white-space: nowrap;", model_name_source)

    def test_workspace_renders_collapsible_thinking_process(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")
        types_source = self.source("frontend/src/api/types.ts")

        self.assertIn("function renderMessageBubble", app_source)
        self.assertIn('message.role === "thinking"', app_source)
        self.assertIn('className="thinking-process"', app_source)
        self.assertIn("<details", app_source)
        self.assertIn("function formatThinkingDuration", app_source)
        self.assertIn("function thinkingSummaryText", app_source)
        self.assertIn("function markStreamingThinkingCompleted", app_source)
        self.assertIn("duration_ms?: number", types_source)
        self.assertIn('className="thinking-duration"', app_source)
        self.assertIn("thinkingSummaryText(message, activelyThinkingTurnId === message.turn_id)", app_source)
        self.assertIn("setActivelyThinkingTurnId(streamingThinking ? response.turn_id : null)", app_source)
        self.assertIn("正在思考", app_source)
        self.assertIn("思考完成", app_source)
        self.assertIn("用时", app_source)
        self.assertNotIn("<1 秒", app_source)
        self.assertIn(".thinking-process", styles_source)
        self.assertIn(".thinking-process summary", styles_source)
        self.assertIn(".thinking-duration", styles_source)
        thinking_source = styles_source.rsplit(".thinking-process {\n  border: 0;", 1)[1].split("}", 1)[0]
        summary_source = styles_source.rsplit(".thinking-process summary {\n  display: inline-flex;", 1)[1].split("}", 1)[0]
        duration_source = styles_source.rsplit(".thinking-duration {\n", 1)[1].split("}", 1)[0]
        markdown_source = styles_source.rsplit(".thinking-process .markdown-content {\n", 1)[1].split("}", 1)[0]
        self.assertIn("font-size: inherit;", thinking_source)
        self.assertIn("font-size: inherit;", summary_source)
        self.assertIn("font-size: inherit;", duration_source)
        self.assertIn("font-size: 0.92em;", markdown_source)
        self.assertNotIn("font-size: inherit;", markdown_source)
        self.assertNotIn("font-size: 13px;", thinking_source)
        self.assertNotIn("font-size: 12px;", summary_source)
        self.assertNotIn("font-size: 12px;", duration_source)

    def test_branch_switch_scrolls_to_branch_start_instead_of_latest_message(self):
        app_source = self.source("frontend/src/App.tsx")
        switch_branch_source = app_source.split("async function switchBranch", 1)[1].split(
            "function branchParentKey", 1
        )[0]

        self.assertIn("function branchSwitchFocusMessageId", app_source)
        self.assertIn("branchSwitchFocusMessageId(message, next)", switch_branch_source)
        self.assertIn("await openConversation(currentSessionId, focusMessageId)", switch_branch_source)
        self.assertNotIn("await openConversation(currentSessionId);", switch_branch_source)
        self.assertIn('return parentKey !== "root" ? parentKey : next.message_id', app_source)

    def test_branch_switch_focus_does_not_draw_green_message_box(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")
        message_bubble_opening = app_source.split('className={`message-bubble ${message.role}`}', 1)[1].split(
            ">",
            1,
        )[0]

        self.assertIn("highlightedMessageId", app_source)
        self.assertIn("function registerMessageElement", app_source)
        self.assertIn("messageRefs.current.set(messageId, node)", app_source)
        self.assertIn("ref={(node) => onRegisterMessageElement(message.message_id, node)}", self.message_bubble_source())
        self.assertNotIn("data-highlighted", message_bubble_opening)
        self.assertNotIn('.message-bubble[data-highlighted="true"]', styles_source)
        self.assertNotIn('.thinking-process[data-highlighted="true"]', styles_source)

    def test_right_workspace_splits_header_and_history_with_message_entry_frames(self):
        styles_source = self.source("frontend/src/styles.css")
        assistant_bubble_source = styles_source.rsplit(".message-bubble.assistant {\n", 1)[1].split("}", 1)[0]
        thinking_source = styles_source.rsplit(".thinking-process {\n  border: 0;", 1)[1].split("}", 1)[0]
        message_list_source = styles_source.rsplit(".message-list {\n  min-height: 0;", 1)[1].split("}", 1)[0]
        entry_bubble_source = styles_source.rsplit(".message-entry .message-bubble {\n", 1)[1].split("}", 1)[0]

        history_surface_source = styles_source.rsplit(".conversation-surface {\n  border: 0;", 1)[1].split(
            "}",
            1,
        )[0]
        stage_source = styles_source.rsplit(".home-workspace-content {\n  --composer-overlay-height: 178px;", 1)[1].split(
            "}",
            1,
        )[0]

        self.assertIn("--line: oklch(89% 0.016 279);", styles_source)
        self.assertIn("--line-strong: oklch(78% 0.034 278);", styles_source)
        self.assertIn("container-type: inline-size;", stage_source)
        self.assertIn("position: relative;", stage_source)
        self.assertNotIn("border-top: 1px solid #000000;", stage_source)
        self.assertIn("padding: 0;", stage_source)
        self.assertNotIn("padding-top: 16px;", stage_source)
        self.assertIn("background: transparent;", stage_source)
        self.assertIn("background: transparent;", history_surface_source)
        self.assertIn(".conversation-surface {\n  border: 0;", styles_source)
        self.assertIn("border: 0;", message_list_source)
        self.assertNotIn("border: 1px solid var(--line);", message_list_source)
        self.assertIn(".message-entry {\n  border: 0;", styles_source)
        self.assertIn("border-color: transparent;", entry_bubble_source)
        self.assertIn(".message-entry.user .message-bubble", styles_source)
        self.assertIn(".message-entry.assistant .message-bubble", styles_source)
        self.assertIn(".thinking-process {\n  border: 0;", styles_source)
        composer_source = styles_source.rsplit(".conversation-composer {\n  position: absolute;", 1)[1].split(
            "}",
            1,
        )[0]
        self.assertIn("border: 1px solid var(--line-strong);", composer_source)
        self.assertIn(".conversation-surface {\n  border: 0;", styles_source)
        self.assertIn(".thinking-process {\n  border: 0;", styles_source)
        self.assertIn("border-radius: var(--radius-control);", assistant_bubble_source)
        self.assertIn("padding: 14px 16px 12px;", assistant_bubble_source)
        self.assertIn("padding: 8px 2px 8px;", thinking_source)
        self.assertIn("box-shadow: none", styles_source)

    def test_conversation_history_is_centered_with_floating_composer(self):
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("width: min(100%, 880px);", styles_source)
        self.assertIn("justify-self: center", styles_source)
        self.assertNotIn("padding: 4px 2px 154px;", styles_source)
        self.assertIn("--chat-scrollbar-gutter: 16px;", styles_source)
        self.assertIn("--chat-column-side-gap: clamp(18px, calc((100cqw - 840px) / 2), 118px);", styles_source)
        self.assertIn("--chat-column-width: min(840px, calc(100cqw - (var(--chat-column-side-gap) * 2)));", styles_source)
        self.assertNotIn("clamp(48px, 5cqw, 84px)", styles_source)
        self.assertNotIn("min(820px", styles_source)
        self.assertNotIn("--chat-column-side-gap: 48px;", styles_source)
        self.assertNotIn("--chat-column-side-gap: 16px;", styles_source)
        self.assertNotIn("--chat-column-side-gap: clamp(14px, 5cqw, 24px);", styles_source)
        self.assertNotIn("padding: 4px 2px 0;", styles_source)
        self.assertGreaterEqual(styles_source.count("width: var(--chat-column-width);"), 3)
        self.assertIn("--chat-scrollbar-axis-offset: 0px;", styles_source)
        self.assertNotIn("--chat-scrollbar-axis-offset: calc((var(--chat-scrollbar-gutter) - 1px) / 2);", styles_source)
        self.assertNotIn("--chat-scrollbar-axis-offset: calc((var(--chat-scrollbar-gutter)) / 2);", styles_source)
        self.assertIn("scrollbar-gutter: stable;", styles_source)
        self.assertNotIn("scrollbar-gutter: stable both-edges;", styles_source)
        self.assertIn(".conversation-surface::-webkit-scrollbar", styles_source)
        self.assertIn("width: var(--chat-scrollbar-gutter);", styles_source)
        self.assertIn("scrollbar-color: color-mix(in oklch, var(--muted) 52%, transparent) transparent;", styles_source)
        self.assertIn(".conversation-surface::-webkit-scrollbar-track", styles_source)
        self.assertIn(".conversation-surface::-webkit-scrollbar-thumb", styles_source)
        self.assertIn("background-clip: content-box;", styles_source)
        composer_source = styles_source.rsplit(".conversation-composer {\n  position: absolute;", 1)[1].split(
            "}",
            1,
        )[0]
        surface_layout_source = styles_source.rsplit(".conversation-surface {\n  display: grid;", 1)[1].split(
            ".message-list,",
            1,
        )[0]
        self.assertIn("scrollbar-gutter: stable;", surface_layout_source)
        self.assertNotIn("scrollbar-gutter: stable both-edges;", surface_layout_source)
        self.assertIn("left: 50%;", composer_source)
        self.assertNotIn("left: calc((100% - var(--chat-scrollbar-gutter)) / 2);", composer_source)
        self.assertIn("bottom: 8px;", composer_source)
        self.assertIn("transform: translateX(-50%);", styles_source)
        self.assertIn("width: var(--chat-column-width);", styles_source)
        self.assertIn("box-shadow: 0 18px 46px oklch(34% 0.035 245 / 0.1);", styles_source)
        self.assertNotIn("width: var(--chat-column-width);\n  box-shadow: none;", styles_source)
        self.assertNotIn("0 -18px 42px", styles_source)
        final_message_list_source = styles_source.rsplit(".message-list {\n  min-height: 0;", 1)[1].split("}", 1)[0]
        self.assertIn("overflow: visible;", final_message_list_source)
        self.assertIn(".message-list::after {\n  display: block;", styles_source)
        self.assertIn("height: var(--composer-overlay-height);", styles_source)
        self.assertIn("content: \"\";", styles_source)
        self.assertNotIn(".home-workspace-content[data-at-latest=\"true\"] .message-list", styles_source)
        self.assertNotIn("translateY(calc(-1 * var(--composer-overlay-height)))", styles_source)
        self.assertIn(".message-entry.assistant,\n.message-bubble.assistant,\n.message-bubble.assistant .markdown-content {\n  width: 100%;", styles_source)
        self.assertIn("grid-template-columns: auto minmax(0, 1fr) auto auto;", styles_source)
        self.assertIn(".conversation-composer .file-button {\n  grid-column: 1;", styles_source)

    def test_conversation_history_and_composer_share_alignment_axis(self):
        styles_source = self.source("frontend/src/styles.css")
        app_source = self.source("frontend/src/App.tsx")
        assistant_bubble_source = styles_source.rsplit(".message-bubble.assistant {\n", 1)[1].split("}", 1)[0]

        surface_layout_source = styles_source.rsplit(".conversation-surface {\n  display: grid;", 1)[1].split(
            ".message-list,",
            1,
        )[0]
        stage_source = styles_source.rsplit(".home-workspace-content {\n  --composer-overlay-height: 178px;", 1)[1].split(
            "}",
            1,
        )[0]
        shared_column_source = styles_source.rsplit(".message-list,\n.conversation-surface .empty-state {", 1)[1].split(
            "}",
            1,
        )[0]
        composer_source = styles_source.rsplit(".conversation-composer {\n  position: absolute;", 1)[1].split(
            "}",
            1,
        )[0]

        self.assertIn("--chat-scrollbar-gutter: 16px;", stage_source)
        self.assertIn("--chat-column-side-gap: clamp(18px, calc((100cqw - 840px) / 2), 118px);", stage_source)
        self.assertNotIn("clamp(48px, 5cqw, 84px)", stage_source)
        self.assertIn("--chat-column-width: min(840px, calc(100cqw - (var(--chat-column-side-gap) * 2)));", stage_source)
        self.assertNotIn("--chat-column-width: calc(100% - (var(--chat-column-side-gap) * 2));", stage_source)
        self.assertNotIn("min(820px", stage_source)
        self.assertNotIn("--chat-column-side-gap: 48px;", styles_source)
        self.assertNotIn("--chat-column-side-gap: 16px;", styles_source)
        self.assertNotIn("--chat-column-side-gap: clamp(14px, 5cqw, 24px);", styles_source)
        self.assertIn("const composerRect = composerRef.current?.getBoundingClientRect();", app_source)
        self.assertIn('stage.style.setProperty("--composer-overlay-height"', app_source)
        self.assertNotIn('conversationStageRef.current?.style.setProperty("--composer-column-width"', app_source)
        self.assertNotIn('conversationStageRef.current?.style.setProperty("--composer-column-offset"', app_source)
        self.assertNotIn("const surfaceRect = conversationSurfaceRef.current?.getBoundingClientRect();", app_source)
        self.assertNotIn("--composer-column-width", styles_source)
        self.assertNotIn("--composer-column-offset", styles_source)
        self.assertIn("new ResizeObserver", app_source)
        self.assertIn("observer.observe(composer)", app_source)
        self.assertIn("container-type: inline-size;", stage_source)
        self.assertNotIn("border-radius: var(--radius-panel);", stage_source)
        self.assertIn("border-radius: inherit;", surface_layout_source)
        self.assertNotIn("border-radius: 0;", stage_source)
        self.assertNotIn("border-radius: 0;", surface_layout_source)
        self.assertIn("padding: 0;", surface_layout_source)
        self.assertIn("overflow-y: auto;", surface_layout_source)
        self.assertNotIn("overflow-y: scroll;", surface_layout_source)
        self.assertIn("scrollbar-gutter: stable;", surface_layout_source)
        self.assertNotIn("scrollbar-gutter: stable both-edges;", surface_layout_source)
        self.assertIn("padding: 14px 16px 12px;", assistant_bubble_source)
        self.assertIn("width: var(--chat-column-width);", shared_column_source)
        self.assertNotIn("justify-self: stretch;", shared_column_source)
        self.assertNotIn("transform: translateX(var(--chat-scrollbar-axis-offset));", shared_column_source)
        self.assertIn("width: var(--chat-column-width);", composer_source)
        self.assertIn("left: 50%;", composer_source)
        self.assertNotIn("left: calc((100% - var(--chat-scrollbar-gutter)) / 2);", composer_source)
        self.assertIn("transform: translateX(-50%);", composer_source)
        self.assertNotIn("--composer-content-inset", styles_source)
        self.assertNotIn("padding-right: 10px;", shared_column_source)
        self.assertNotIn("padding-right: 8px;", shared_column_source)

    def test_chat_and_favorite_scrollers_keep_border_space_clear_of_scrollbars(self):
        styles_source = self.source("frontend/src/styles.css")

        stage_source = styles_source.rsplit(".home-workspace-content {\n  --composer-overlay-height: 178px;", 1)[1].split(
            "}",
            1,
        )[0]
        surface_layout_source = styles_source.rsplit(".conversation-surface {\n  display: grid;", 1)[1].split(
            ".conversation-surface::-webkit-scrollbar",
            1,
        )[0]
        shared_column_source = styles_source.rsplit(".message-list,\n.conversation-surface .empty-state {", 1)[1].split(
            "}",
            1,
        )[0]
        favorite_list_source = styles_source.split(".favorites-workspace .favorite-list {", 1)[1].split(
            "}",
            1,
        )[0]
        favorite_row_source = styles_source.split(".favorite-selection-row {", 1)[1].split(
            "}",
            1,
        )[0]

        self.assertIn("--chat-border-safe-space: 4px;", stage_source)
        self.assertIn("padding: 0;", surface_layout_source)
        self.assertIn(
            "width: var(--chat-column-width);",
            shared_column_source,
        )
        self.assertIn("--favorite-list-border-safe-space: 4px;", favorite_list_source)
        self.assertIn(
            "padding-inline: var(--favorite-list-border-safe-space) calc(var(--favorite-list-border-safe-space) + 4px);",
            favorite_list_source,
        )
        self.assertIn(
            "width: calc(100% + var(--favorite-list-end-compensation) - var(--favorite-list-border-safe-space));",
            favorite_row_source,
        )

    def test_new_conversation_message_entries_keep_stable_history_width(self):
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn(".home-workspace-content {\n  --composer-overlay-height: 178px;", styles_source)
        self.assertIn(".conversation-surface {\n  display: grid;", styles_source)
        self.assertIn(
            ".message-list,\n.conversation-surface .empty-state {\n  width: var(--chat-column-width);",
            styles_source,
        )
        message_entry_source = styles_source.split(".message-entry {\n", 1)[1].split("}", 1)[0]
        message_list_source = styles_source.rsplit(".message-list {\n  min-height: 0;", 1)[1].split("}", 1)[0]
        self.assertIn("display: grid;", message_entry_source)
        self.assertIn("border: 1px solid transparent;", message_entry_source)
        self.assertIn("gap: 8px;", message_entry_source)
        self.assertIn("width: 100%;", message_entry_source)
        self.assertIn("border: 0;", message_list_source)
        self.assertNotIn("border: 1px solid var(--line);", message_list_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", styles_source)
        self.assertIn(".message-entry.user {\n  justify-self: stretch;", styles_source)
        self.assertIn(".message-entry.assistant {\n  justify-self: stretch;", styles_source)
        self.assertIn(".message-entry.user .message-bubble {\n  width: fit-content;\n  max-width: min(78%, 680px);", styles_source)

    def test_branch_controls_use_unboxed_arrows_below_message_text(self):
        conversation_surface_source = self.source(
            "frontend/src/features/conversations/ConversationWorkspaceSurface.tsx"
        )
        branch_controls_source = self.source("frontend/src/features/conversations/BranchControls.tsx")
        styles_source = self.source("frontend/src/styles.css")

        branch_source = conversation_surface_source.split("function renderBranchControls", 1)[1].split(
            "function renderComposerModelControl", 1
        )[0]
        self.assertIn("<BranchControls", branch_source)
        self.assertIn('aria-label="切换到上一条分支"', branch_controls_source)
        self.assertIn('aria-label="切换到下一条分支"', branch_controls_source)
        self.assertIn("ChevronLeftIcon", branch_controls_source)
        self.assertIn("ChevronRightIcon", branch_controls_source)
        self.assertIn(".branch-controls button {\n  display: inline-grid;", styles_source)
        self.assertIn("border: 0;", styles_source)
        self.assertIn("background: transparent;", styles_source)

    def test_assistant_message_actions_use_deepseek_style_icon_buttons(self):
        app_source = self.source("frontend/src/App.tsx")
        icons_source = self.source("frontend/src/components/icons.tsx")

        assistant_action_source = app_source.split('{message.role === "assistant" ? (', 1)[1].split(
            "</>",
            1,
        )[0]
        self.assertIn("function RegenerateIcon", icons_source)
        self.assertIn("function BranchIcon", icons_source)
        self.assertIn("function StarIcon", icons_source)
        self.assertIn("<RegenerateIcon />", assistant_action_source)
        self.assertIn("branchingFromThisMessage", app_source)
        self.assertIn('{branchingFromThisMessage ? <span className="copy-success-icon">✓</span> : <BranchIcon />}', assistant_action_source)
        self.assertIn("<StarIcon filled={favorited} />", assistant_action_source)
        self.assertIn('aria-label="重新生成"', assistant_action_source)
        self.assertIn('aria-label={branchingFromThisMessage ? "已选择分支起点" : "创建分支"}', assistant_action_source)
        self.assertIn('aria-label={favorited ? "取消收藏回答" : "收藏回答"}', assistant_action_source)
        self.assertNotIn(">重新生成<", assistant_action_source)
        self.assertNotIn(">分支<", assistant_action_source)
        self.assertNotIn(">收藏回答<", assistant_action_source)

    def test_user_message_toolbar_uses_deepseek_style_icons_and_selection_quote_popover(self):
        app_source = self.source("frontend/src/App.tsx")
        panel_source = self.source("frontend/src/features/conversations/ConversationWorkspacePanel.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn('className={`message-entry ${message.role}`}', app_source)
        self.assertIn('className={`message-bubble ${message.role}`}', app_source)
        self.assertIn('className={`message-actions ${message.role}-actions`}', app_source)
        self.assertIn('aria-label="复制消息"', app_source)
        self.assertIn('aria-label="编辑消息"', app_source)
        self.assertIn("<CopyIcon />", app_source)
        self.assertIn("<EditIcon />", app_source)
        self.assertIn("copiedMessageId", app_source)
        self.assertIn("function copyMessage", app_source)
        self.assertIn("setCopiedMessageId(message.message_id)", app_source)
        self.assertIn('className="copy-success-icon"', app_source)
        self.assertIn("✓", app_source)
        self.assertNotIn("☑️", app_source)
        self.assertIn('className="selection-quote-popover"', app_source)
        self.assertIn("onUpdateQuoteSelection={messageActions.updateQuoteSelection}", panel_source)
        self.assertIn("onMouseUp={() => onUpdateQuoteSelection(message)}", self.message_bubble_source())
        self.assertIn("onKeyUp={() => onUpdateQuoteSelection(message)}", self.message_bubble_source())
        self.assertIn(".message-entry.user .message-bubble", styles_source)
        self.assertIn(".message-icon-button", styles_source)
        self.assertIn(".selection-quote-popover", styles_source)
        self.assertIn("button.selection-quote-popover:hover:not(:disabled)", styles_source)
        self.assertIn("transform: translate(-50%, calc(-100% - 10px));", styles_source)
        self.assertIn("button:hover:not(:disabled) {\n  transform: none;", styles_source)

    def test_conversation_client_exposes_authenticated_sse_stream_parser(self):
        conversation_api_source = (
            self.root / "frontend" / "src" / "api" / "conversationApi.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("function streamConversation", conversation_api_source)
        self.assertIn("/conversations/streams/", conversation_api_source)
        self.assertIn("streamId", conversation_api_source)
        self.assertIn('"Accept": "text/event-stream"', conversation_api_source)
        self.assertIn("getSessionToken", conversation_api_source)
        self.assertIn("Authorization", conversation_api_source)
        self.assertIn("thinking_delta", conversation_api_source)
        self.assertIn("content_delta", conversation_api_source)
        self.assertIn("reader.read()", conversation_api_source)
        self.assertIn("yieldToBrowserPaint", conversation_api_source)
        self.assertIn("requestAnimationFrame", conversation_api_source)

    def test_workspace_streams_thinking_and_answer_before_refreshing_detail(self):
        app_source = self.source("frontend/src/App.tsx")

        self.assertIn("startResponseStream", app_source)
        self.assertIn("applyStreamDelta", app_source)
        self.assertIn('event.event === "thinking_delta"', app_source)
        self.assertIn('event.event === "content_delta"', app_source)
        self.assertIn("streamingAssistant", app_source)
        self.assertIn("streamingThinking", app_source)
        self.assertIn("await startResponseStream(response)", app_source)
        self.assertIn("function finishActiveStream(streamId: string)", app_source)
        self.assertIn("finishActiveStream(response.stream_id)", app_source)
        self.assertIn("function shouldHideAssistantPlaceholderDuringThinking", app_source)
        self.assertIn("activelyThinkingTurnId === message.turn_id", app_source)
        self.assertIn("message.role === \"assistant\" &&", app_source)
        self.assertIn("message.status === \"streaming\" &&", app_source)
        self.assertIn("!message.content", app_source)
        render_source = app_source.split("function renderMessageBubble", 1)[1].split(
            "function renderMainWorkspace",
            1,
        )[0]
        self.assertIn("if (shouldHideAssistantPlaceholderDuringThinking(message)) {", render_source)
        self.assertIn("return null;", render_source)

    def test_regenerate_consumes_stream_before_refreshing_detail(self):
        conversation_workspace_source = self.source("frontend/src/features/conversations/useConversationWorkspace.ts")
        styles_source = self.source("frontend/src/styles.css")
        regenerate_source = conversation_workspace_source.split("async function regenerate", 1)[1].split(
            "return {",
            1,
        )[0]

        self.assertIn("const response = await apiClient.regenerateMessage", regenerate_source)
        self.assertIn("showRegeneratingTurn(response, message)", regenerate_source)
        self.assertIn("await startResponseStream(response)", regenerate_source)
        self.assertIn("await openConversation(response.session_id)", regenerate_source)
        self.assertNotIn("setHighlightedMessageId", regenerate_source)
        self.assertNotIn('.message-bubble[data-highlighted="true"]', styles_source)
        self.assertNotIn('.thinking-process[data-highlighted="true"]', styles_source)

    def test_generation_can_be_cancelled_and_regenerate_discards_partial_output(self):
        app_source = self.source("frontend/src/App.tsx")
        conversation_api_source = (
            self.root / "frontend" / "src" / "api" / "conversationApi.ts"
        ).read_text(encoding="utf-8")
        types_source = (self.root / "frontend" / "src" / "api" / "types.ts").read_text(encoding="utf-8")

        self.assertIn("function cancelTurn", conversation_api_source)
        self.assertIn("/turns/", conversation_api_source)
        self.assertIn("/cancel", conversation_api_source)
        self.assertIn("partial_content", conversation_api_source)
        self.assertIn("partial_thinking", conversation_api_source)
        self.assertIn('"cancelled"', types_source)
        self.assertIn("AbortController", app_source)
        self.assertIn("activeStreamRef", app_source)
        self.assertIn("function currentStreamingContent", app_source)
        self.assertIn("async function cancelActiveGeneration", app_source)
        self.assertIn("preservePartial: true", app_source)
        self.assertIn("preservePartial: false", app_source)
        self.assertIn("停止生成", app_source)
        self.assertIn("<StopIcon />", app_source)
        self.assertIn('className="command-button send-button stop-button"', app_source)
        self.assertIn('if (event.event === "cancelled")', app_source)
        self.assertIn('if (event.event === "failed")', app_source)
        self.assertIn("isStreamingAssistant(message)", app_source)
        self.assertIn("regenerateTargetMessageId(message)", app_source)

    def test_favorites_show_metadata_and_return_to_source_message(self):
        favorites_source = self.source("frontend/src/features/favorites/FavoritesWorkspace.tsx")
        favorite_panel_source = self.source("frontend/src/features/favorites/FavoritesWorkspacePanel.tsx")
        route_content_source = self.source("frontend/src/features/conversations/WorkspaceRouteContent.tsx")
        lifecycle_source = self.source("frontend/src/features/conversations/useConversationLifecycle.ts")
        message_bubble_source = self.source("frontend/src/features/conversations/ConversationMessageBubble.tsx")

        self.assertIn("formatFavoriteSourceType", favorites_source)
        self.assertIn("formatDateTime", favorites_source)
        self.assertIn("setHighlightedMessageId(sourceMessageId)", lifecycle_source)
        self.assertIn("data-highlighted", message_bubble_source)
        self.assertIn("onOpenConversation(favoriteDetail.source_session_id, favoriteDetail.source_id)", favorites_source)
        self.assertIn("onOpenConversation={lifecycle.openFavoriteSourceConversation}", route_content_source)
        self.assertIn("void onOpenConversation(sessionId, sourceMessageId)", favorite_panel_source)

    def test_favorites_page_uses_sidebar_drawer_toggle_at_shared_breakpoint(self):
        hook_source = self.source("frontend/src/app/useResponsiveSidebar.ts")
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        page_model_source = self.source("frontend/src/features/conversations/useWorkspacePageModel.ts")
        route_content_source = self.source("frontend/src/features/conversations/WorkspaceRouteContent.tsx")
        route_shell_source = self.source("frontend/src/app/WorkspaceRouteShell.tsx")
        styles_source = self.source("frontend/src/styles.css")
        toggle_source = route_shell_source.split("function renderSidebarToggle", 1)[1].split(
            "return {",
            1,
        )[0]
        drawer_source = styles_source.split("@media (max-width: 1000px)", 1)[1].split("@media", 1)[0]

        self.assertIn('SIDEBAR_COMPACT_MEDIA = "(max-width: 1000px)"', hook_source)
        self.assertIn("workspaceShell", page_model_source)
        self.assertNotIn('workspaceShell.renderSidebarToggle("favorites-sidebar-toggle")', workspace_source)
        self.assertIn('workspaceShell.renderSidebarToggle("favorites-sidebar-toggle")', route_content_source)
        self.assertIn('aria-expanded={sidebarToggleExpanded}', toggle_source)
        self.assertIn('aria-label={sidebarToggleLabel}', toggle_source)
        self.assertIn('onClick={toggleSidebarFromMain}', toggle_source)
        self.assertIn('"favorites-sidebar-toggle"', route_content_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", drawer_source)
        self.assertIn('.patient-shell[data-mobile-sidebar-open="true"] .patient-sidebar', drawer_source)
        self.assertNotIn(".workspace-panel:not(.home-workspace)", drawer_source)

    def test_favorites_multi_select_toolbar_does_not_auto_select_items(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")
        favorites_source = self.source("frontend/src/features/favorites/FavoritesWorkspace.tsx")

        multi_select_button_source = app_source.split('className="favorite-multi-select-button"', 1)[0].rsplit(
            "<button",
            1,
        )[1]
        self.assertIn("favoriteSelectionMode", app_source)
        self.assertIn('className="favorite-bulk-actions"', app_source)
        self.assertIn('"全选收藏"', app_source)
        self.assertIn('"取消全选收藏"', app_source)
        self.assertIn('"批量设置标签"', app_source)
        self.assertIn('"删除选中的收藏"', app_source)
        self.assertIn("allFavoritesSelected ? \"取消全选\" : \"全选\"", app_source)
        self.assertIn("favoriteSelectionMode ? `已选择 ${selectedCount} 条` : \"收藏\"", favorites_source)
        toolbar_title_source = favorites_source.split('className="favorite-toolbar-title"', 1)[1].split(
            "</strong>",
            1,
        )[0]
        self.assertNotIn("收藏列表", toolbar_title_source)
        self.assertIn("favorites.map((favorite) => favorite.favorite_id)", app_source)
        self.assertNotIn("setSelectedFavoriteIds", multi_select_button_source)
        self.assertNotIn("favorites.map((favorite) => favorite.favorite_id)", multi_select_button_source)
        self.assertLess(favorites_source.index('className="favorite-list"'), favorites_source.index("{favoriteBulkActions}"))
        self.assertIn("grid-template-rows: minmax(0, 1fr) auto;", styles_source)
        self.assertIn(".favorite-list-panel .favorite-bulk-actions", styles_source)
        multi_select_button_style = styles_source.split(".favorite-multi-select-button {", 1)[1].split("}", 1)[0]
        self.assertIn("width: 34px;", multi_select_button_style)
        self.assertIn("min-width: 34px;", multi_select_button_style)
        self.assertIn("min-height: 34px;", multi_select_button_style)

    def test_favorites_prd_matches_current_implemented_scope(self):
        favorites_prd = (
            self.root / "docs" / "releases" / "v0.1.0" / "prd" / "favorites.md"
        ).read_text(encoding="utf-8")
        favorites_technical = (
            self.root / "docs" / "releases" / "v0.1.0" / "technical" / "favorites.md"
        ).read_text(encoding="utf-8")
        acceptance = (self.root / "docs" / "releases" / "v0.1.0" / "acceptance.md").read_text(
            encoding="utf-8"
        )
        favorite_actions_source = self.source("frontend/src/features/favorites/useFavoriteMessageActions.ts")
        favorite_workspace_source = self.source("frontend/src/features/favorites/FavoritesWorkspace.tsx")
        favorite_state_source = self.source("frontend/src/features/favorites/useFavoriteWorkspace.ts")
        conversation_repository_source = (
            self.root / "backend" / "app" / "repositories" / "conversation_repository.py"
        ).read_text(encoding="utf-8")

        self.assertIn("首页对话中每条助手回答底部的收藏按钮", favorites_prd)
        self.assertNotIn("首页对话中每条助手最终回答底部的收藏按钮", favorites_prd)
        self.assertIn("系统校验来源消息属于当前 `account`、当前会话且为助手消息。", favorites_prd)
        self.assertNotIn("助手最终回复", favorites_prd)
        self.assertIn("用户可从原回答取消收藏；收藏页通过批量选择模式删除选中收藏。", favorites_prd)
        self.assertNotIn("用户可从原回答或收藏页取消收藏。", favorites_prd)
        self.assertNotIn("| 加载中 | 展示列表加载状态 |", favorites_prd)
        self.assertNotIn("| 加载失败 | 展示错误提示和重试入口 |", favorites_prd)

        self.assertIn("后端必须校验 `source_id` 是该会话内的助手消息。", favorites_technical)
        self.assertNotIn("后端必须校验 `source_id` 是该会话内可收藏的助手最终回复。", favorites_technical)
        self.assertIn("当前前端的单条取消收藏入口在原回答收藏按钮上", favorites_technical)
        self.assertIn("用户可在原回答上取消收藏；收藏页通过批量选择模式删除选中收藏。", acceptance)

        self.assertIn("apiClient.deleteFavorite(existing.favorite_id)", favorite_actions_source)
        self.assertNotIn("apiClient.deleteFavorite", favorite_workspace_source)
        self.assertIn("apiClient.batchDeleteFavorites(selectedFavoriteIds)", favorite_state_source)
        self.assertIn('message["role"] != "assistant"', conversation_repository_source)
        self.assertNotIn('message["status"] != "completed"', conversation_repository_source)

    def test_favorites_selection_mode_places_check_controls_left_and_centers_status(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")
        favorites_source = self.source("frontend/src/features/favorites/FavoritesWorkspace.tsx")
        card_top_source = favorites_source.split('className="favorite-card-top"', 1)[1].split(
            'className="favorite-summary"',
            1,
        )[0]

        self.assertIn('className="favorite-toolbar-title"', favorites_source)
        self.assertIn("favoriteSelectionMode ? `已选择 ${selectedCount} 条`", favorites_source)
        self.assertIn('className="favorite-selection-cancel-button"', favorites_source)
        self.assertIn('className={rowClassName}', favorites_source)
        self.assertIn('"favorite-selection-row"', favorites_source)
        self.assertLess(favorites_source.index('className="favorite-card-check-frame"'), favorites_source.index('className={cardClassName}'))
        self.assertNotIn("favorite-card-check", card_top_source)
        self.assertIn('.favorite-toolbar[data-selection-mode="true"]', styles_source)
        self.assertIn(
            "grid-template-columns: minmax(var(--workspace-titlebar-side), 1fr) auto minmax(var(--workspace-titlebar-side), 1fr);",
            styles_source,
        )
        self.assertIn(".favorite-toolbar-title", styles_source)
        self.assertIn("justify-self: center;", styles_source)
        self.assertIn(".favorite-selection-row", styles_source)
        self.assertIn("grid-template-columns: 34px minmax(0, 1fr);", styles_source)

    def test_favorites_total_count_sits_below_last_list_card(self):
        styles_source = self.source("frontend/src/styles.css")
        favorites_source = self.source("frontend/src/features/favorites/FavoritesWorkspace.tsx")
        toolbar_source = favorites_source.split('className="favorite-toolbar"', 1)[1].split(
            'className="favorite-list"',
            1,
        )[0]

        self.assertIn("`共 ${favorites.length} 条`", favorites_source)
        self.assertNotIn("`共 ${favorites.length} 条收藏`", favorites_source)
        self.assertNotIn("共 ${favorites.length} 条", toolbar_source)
        self.assertLess(favorites_source.index("favorites.map((favorite) => {"), favorites_source.index('className="favorite-list-count"'))
        self.assertIn(".favorite-list-count", styles_source)

    def test_favorites_list_extends_through_scrollbar_gutter_to_match_toolbar(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")
        favorites_source = self.source("frontend/src/features/favorites/FavoritesWorkspace.tsx")
        favorite_list_source = styles_source.split(".favorites-workspace .favorite-list {", 1)[1].split(
            "}",
            1,
        )[0]
        favorite_row_source = styles_source.split(".favorite-selection-row {", 1)[1].split(
            "}",
            1,
        )[0]
        toolbar_source = styles_source.split(".favorites-workspace .favorite-toolbar {", 1)[1].split(
            "}",
            1,
        )[0]
        bulk_source = styles_source.split(".favorite-list-panel .favorite-bulk-actions {", 1)[1].split(
            "}",
            1,
        )[0]

        self.assertIn("const favoriteListPanelRef = useRef<HTMLElement | null>(null)", app_source)
        self.assertIn("const favoriteListRef = useRef<HTMLDivElement | null>(null)", app_source)
        self.assertIn("function updateFavoriteListAlignment()", app_source)
        self.assertIn("list.offsetWidth - list.clientWidth - listHorizontalBorderWidth", app_source)
        self.assertIn('"--favorite-list-end-compensation",', app_source)
        self.assertIn('ref={favoriteListPanelRef}', favorites_source)
        self.assertIn('ref={favoriteListRef}', favorites_source)
        self.assertIn("--favorite-list-end-compensation: 0px;", styles_source)
        self.assertIn(
            "width: calc(100% + var(--favorite-list-end-compensation) - var(--favorite-list-border-safe-space));",
            favorite_row_source,
        )
        self.assertNotIn("margin-inline-end: var(--favorite-list-end-compensation);", toolbar_source)
        self.assertNotIn("margin-inline-end: var(--favorite-list-end-compensation);", bulk_source)
        self.assertIn("overflow-x: hidden;", favorite_list_source)
        self.assertIn("overflow-y: auto;", favorite_list_source)
        self.assertNotIn("overflow: auto;", favorite_list_source)
        self.assertIn(
            "padding-inline: var(--favorite-list-border-safe-space) calc(var(--favorite-list-border-safe-space) + 4px);",
            favorite_list_source,
        )
        self.assertIn("scrollbar-gutter: stable;", favorite_list_source)

    def test_favorites_420_to_650_uses_single_column_with_detail_drawer(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")
        favorites_source = self.source("frontend/src/features/favorites/FavoritesWorkspace.tsx")
        narrow_favorites_source = styles_source.rsplit("@media (max-width: 650px)", 1)[1].split(
            "\n}\n\n.brand-row",
            1,
        )[0]

        self.assertIn('className="favorite-detail-back-button"', favorites_source)
        self.assertIn('aria-label="返回收藏列表"', favorites_source)
        self.assertIn("onClick={closeFavoriteDetail}", favorites_source)
        self.assertIn("<SidebarBackIcon />", favorites_source)
        self.assertNotIn("<BackIcon />", favorites_source)
        self.assertNotIn("<span>返回收藏列表</span>", favorites_source)
        self.assertIn("function closeFavoriteDetail", app_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", narrow_favorites_source)
        self.assertIn(".favorites-workspace .favorite-detail-empty", narrow_favorites_source)
        self.assertIn("display: none;", narrow_favorites_source)
        self.assertIn(".favorites-workspace .favorite-detail:not(.favorite-detail-empty)", narrow_favorites_source)
        self.assertIn("position: absolute;", narrow_favorites_source)
        self.assertIn("inset: 0;", narrow_favorites_source)
        self.assertIn("animation: favorite-detail-slide-in", narrow_favorites_source)
        self.assertIn("@keyframes favorite-detail-slide-in", styles_source)
        self.assertIn("translateX(100%)", styles_source)

    def test_favorite_tags_are_capsules_with_inline_edit_controls(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("function FavoriteTagCapsules", app_source)
        self.assertIn('className="favorite-tag-capsules"', app_source)
        self.assertIn('className="favorite-tag-pill"', app_source)
        self.assertIn('className="favorite-tag-edit-button"', app_source)
        self.assertIn('className="favorite-tag-remove-button"', app_source)
        self.assertIn('className="favorite-tag-add-button"', app_source)
        self.assertIn("editingFavoriteTagIds", app_source)
        self.assertIn("appendFavoriteTag", app_source)
        self.assertIn("removeFavoriteTag", app_source)
        self.assertIn("saveFavoriteTags(favoriteId", app_source)
        self.assertIn(".favorite-tag-capsules", styles_source)
        self.assertIn(".favorite-tag-pill", styles_source)
        self.assertIn(".favorite-tag-edit-button", styles_source)
        self.assertIn(".favorite-tag-remove-button", styles_source)
        self.assertIn(".favorite-tag-add-button", styles_source)

    def test_favorite_list_cards_place_metadata_and_tags_below_summary(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")

        card_source = app_source.split('className={cardClassName}', 1)[1].split(
            "</article>",
            1,
        )[0]
        self.assertIn('className="favorite-card-meta-row"', card_source)
        self.assertIn('className="favorite-card-tag-row"', card_source)
        self.assertLess(card_source.index('className="favorite-card-top"'), card_source.index('className="favorite-summary"'))
        self.assertLess(card_source.index('className="favorite-summary"'), card_source.index('className="favorite-card-meta-row"'))
        self.assertLess(card_source.index('className="favorite-card-meta-row"'), card_source.index('className="favorite-card-tag-row"'))
        meta_row_source = card_source.split('className="favorite-card-meta-row"', 1)[1].split("</div>", 1)[0]
        self.assertLess(meta_row_source.index("formatFavoriteSourceType(favorite.source_type)"), meta_row_source.index("formatDateTime(favorite.created_at)"))

        self.assertIn(".favorite-card-meta-row", styles_source)
        self.assertIn("justify-content: space-between", styles_source)
        self.assertIn(".favorite-card-tag-row", styles_source)

    def test_favorite_detail_metadata_and_tags_sit_under_title_and_auto_save(self):
        app_source = self.source("frontend/src/App.tsx")

        detail_source = app_source.split('className="favorite-detail-header"', 1)[1].split(
            'className="favorite-detail-body"',
            1,
        )[0]
        self.assertIn('className="favorite-detail-meta-row"', detail_source)
        self.assertIn('className="favorite-detail-tag-row"', detail_source)
        self.assertLess(detail_source.index("<h2>{favoriteDetail.title}</h2>"), detail_source.index('className="favorite-detail-meta-row"'))
        self.assertLess(detail_source.index('className="favorite-detail-meta-row"'), detail_source.index('className="favorite-detail-tag-row"'))
        self.assertLess(detail_source.index('className="favorite-detail-tag-row"'), detail_source.index("FavoriteTagCapsules"))
        meta_row_source = detail_source.split('className="favorite-detail-meta-row"', 1)[1].split("</div>", 1)[0]
        self.assertLess(meta_row_source.index("formatFavoriteSourceType(favoriteDetail.source_type)"), meta_row_source.index("formatDateTime(favoriteDetail.created_at)"))
        self.assertIn("favoriteDetailAutoSaveRef", app_source)
        self.assertIn('document.addEventListener("pointerdown"', app_source)
        self.assertIn("flushFavoriteDetailTags", app_source)
        self.assertNotIn("保存标签", detail_source)
        self.assertNotIn('id="favorite-tags-input"', app_source)

    def test_favorite_titles_are_larger_than_markdown_h1(self):
        import re

        styles_source = self.source("frontend/src/styles.css")

        def font_size(selector: str) -> float:
            marker = f"{selector} {{"
            self.assertIn(marker, styles_source)
            body = styles_source.split(marker, 1)[1].split("}", 1)[0]
            match = re.search(r"font-size:\s*([0-9.]+)px", body)
            if match:
                return float(match.group(1))
            variable_match = re.search(r"font-size:\s*var\((--[^)]+)\)", body)
            self.assertIsNotNone(variable_match, body)
            variable_definition = re.search(
                rf"{re.escape(variable_match.group(1))}:\s*([0-9.]+)px;",
                styles_source,
            )
            self.assertIsNotNone(variable_definition, variable_match.group(1))
            return float(variable_definition.group(1))

        self.assertGreater(
            font_size(".favorites-workspace .favorite-card-title"),
            font_size(".favorite-summary .markdown-content h1"),
        )
        self.assertGreater(
            font_size(".favorite-detail h2"),
            font_size(".favorite-detail-body .markdown-content h1"),
        )

    def test_chat_history_and_composer_share_column_center_with_edge_scrollbar(self):
        styles_source = self.source("frontend/src/styles.css")
        app_source = self.source("frontend/src/App.tsx")

        composer_source = styles_source.rsplit(".conversation-composer {\n  position: absolute;", 1)[1].split("}", 1)[0]
        scrollbar_source = styles_source.split(".conversation-surface::-webkit-scrollbar {", 1)[1].split("}", 1)[0]

        shared_column_source = styles_source.rsplit(".message-list,\n.conversation-surface .empty-state {", 1)[1].split(
            "}",
            1,
        )[0]

        self.assertIn("--chat-scrollbar-axis-offset: 0px;", styles_source)
        self.assertNotIn("--chat-scrollbar-axis-offset: calc((var(--chat-scrollbar-gutter) - 1px) / 2);", styles_source)
        self.assertNotIn("--chat-scrollbar-axis-offset: calc((var(--chat-scrollbar-gutter)) / 2);", styles_source)
        self.assertIn("const surfaceStyle = window.getComputedStyle(surface);", app_source)
        self.assertIn("const surfaceHorizontalBorderWidth =", app_source)
        self.assertIn("const actualScrollbarGutter = Math.max(", app_source)
        self.assertIn('stage.style.setProperty("--chat-scrollbar-axis-offset", `${actualScrollbarGutter / 2}px`);', app_source)
        self.assertIn("left: 50%", composer_source)
        self.assertNotIn("left: calc((100% - var(--chat-scrollbar-gutter)) / 2)", composer_source)
        self.assertIn("width: var(--chat-column-width)", composer_source)
        self.assertIn("transform: translateX(-50%)", composer_source)
        self.assertNotIn("transform: translateX(var(--chat-scrollbar-axis-offset))", shared_column_source)
        self.assertIn("width: var(--chat-scrollbar-gutter)", scrollbar_source)

    def test_conversation_messages_render_markdown(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")
        package_source = (self.root / "frontend" / "package.json").read_text(encoding="utf-8")

        self.assertIn('import ReactMarkdown from "react-markdown"', app_source)
        self.assertIn("function renderMarkdownContent", app_source)
        self.assertGreaterEqual(app_source.count("renderMarkdownContent(message.content)"), 2)
        self.assertIn("renderMarkdownContent(favorite.content_summary)", app_source)
        self.assertIn("renderMarkdownContent(favoriteDetail.content_snapshot ?? favoriteDetail.content_summary)", app_source)
        self.assertNotIn("<p>{message.content}</p>", app_source)
        self.assertIn('className="markdown-content"', app_source)
        self.assertIn(".markdown-content", styles_source)
        self.assertIn('"react-markdown"', package_source)

    def test_conversation_history_scrolls_above_pinned_composer(self):
        app_source = self.source("frontend/src/App.tsx")
        home_workspace_source = self.home_workspace_source()
        conversation_surface_source = self.source(
            "frontend/src/features/conversations/ConversationWorkspaceSurface.tsx"
        )
        composer_source = self.conversation_composer_source()
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn('className="workspace-panel home-workspace"', app_source)
        self.assertIn("conversationStageRef", app_source)
        self.assertIn("conversationSurfaceRef", app_source)
        self.assertIn('className="home-workspace-content"', app_source)
        self.assertIn('className="conversation-surface"', app_source)
        self.assertNotIn("data-at-latest", app_source)
        self.assertNotIn("conversationAtLatest", app_source)
        self.assertIn("ref={conversationStageRef}", app_source)
        self.assertIn("ref={conversationSurfaceRef}", app_source)
        self.assertLess(
            app_source.index('className="home-workspace-content"'),
            app_source.index('className="conversation-surface"'),
        )
        self.assertLess(
            home_workspace_source.index('className="conversation-surface"'),
            home_workspace_source.index("{composer}"),
        )
        self.assertLess(
            home_workspace_source.index("{composer}"),
            home_workspace_source.index("{quoteSelection ?"),
        )
        self.assertIn("composer={renderConversationComposer()}", conversation_surface_source)
        self.assertIn('className="assistant-composer conversation-composer"', composer_source)
        self.assertIn(".home-workspace", styles_source)
        self.assertIn("display: flex;", styles_source)
        home_workspace_source = styles_source.rsplit(".home-workspace {\n  display: flex;", 1)[1].split(
            "}",
            1,
        )[0]
        self.assertIn("gap: 0;", home_workspace_source)
        self.assertIn(".conversation-surface", styles_source)
        floating_layout_source = styles_source.rsplit(".conversation-surface {\n  display: grid;", 1)[1]
        surface_layout_source = floating_layout_source.split(".message-list,", 1)[0]
        self.assertIn("height: 100%;", surface_layout_source)
        self.assertIn("align-content: start;", surface_layout_source)
        self.assertIn("overflow-y: auto;", surface_layout_source)
        self.assertNotIn("overflow-y: scroll;", surface_layout_source)
        self.assertIn("overflow-x: hidden;", surface_layout_source)
        self.assertIn("scrollbar-gutter: stable;", surface_layout_source)
        self.assertNotIn("scrollbar-gutter: stable both-edges;", surface_layout_source)
        self.assertIn(".message-list", styles_source)
        self.assertIn("overflow: visible;", floating_layout_source)
        self.assertIn(".message-list::after", styles_source)
        self.assertNotIn(".home-workspace-content[data-at-latest=\"true\"] .message-list", styles_source)
        self.assertIn(".assistant-composer", styles_source)
        self.assertIn(".conversation-composer {\n  position: absolute;", styles_source)

    def test_user_message_editing_happens_inline_in_message_textbox(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("editingMessageId", app_source)
        self.assertIn("editingMessageText", app_source)
        self.assertIn("function submitEditedUserMessage", app_source)
        self.assertIn('className="message-edit-form"', app_source)
        self.assertIn('aria-label="编辑历史提问"', app_source)
        self.assertIn('aria-label="编辑消息"', app_source)
        self.assertNotIn("编辑重发", app_source)
        message_edit_source = self.message_bubble_source().split('className="message-edit-form"', 1)[1].split(
            'className={`message-actions ${message.role}-actions`}',
            1,
        )[0]
        self.assertIn("取消", message_edit_source)
        self.assertIn("onClick={onCancelEditingMessage}", message_edit_source)
        self.assertIn('{sending ? "发送中..." : "发送"}', message_edit_source)
        self.assertNotIn("发送编辑", message_edit_source)
        self.assertNotIn("取消编辑", message_edit_source)
        self.assertIn('className="message-edit-button message-edit-cancel-button"', message_edit_source)
        self.assertIn('className="message-edit-button message-edit-send-button"', message_edit_source)
        self.assertNotIn('className="secondary-button message-edit-button message-edit-cancel-button"', message_edit_source)
        self.assertNotIn('className="command-button message-edit-button message-edit-send-button"', message_edit_source)
        self.assertIn(".message-bubble.user .message-edit-form", styles_source)
        self.assertIn(".message-bubble.user .message-edit-form textarea", styles_source)
        self.assertIn(".message-edit-actions .message-edit-button", styles_source)
        self.assertIn(".message-bubble.user .message-edit-cancel-button", styles_source)
        self.assertIn(".message-bubble.user .message-edit-send-button", styles_source)
        self.assertIn("background: transparent", styles_source)
        self.assertIn("color: inherit", styles_source)
        self.assertIn("font: inherit", styles_source)
        self.assertIn("padding: 0", styles_source)
        self.assertIn("border: 0", styles_source)
        edit_action_button_source = styles_source.split(".message-edit-actions .message-edit-button {", 1)[1].split(
            "}",
            1,
        )[0]
        edit_cancel_source = styles_source.split(".message-bubble.user .message-edit-cancel-button {", 1)[1].split(
            "}",
            1,
        )[0]
        edit_send_source = styles_source.split(".message-bubble.user .message-edit-send-button {", 1)[1].split(
            "}",
            1,
        )[0]
        self.assertIn("width: 64px;", edit_action_button_source)
        self.assertIn("min-width: 64px;", edit_action_button_source)
        self.assertIn("min-height: 34px;", edit_action_button_source)
        self.assertIn("font-size: var(--text-ui);", edit_action_button_source)
        self.assertIn("border: 1px solid transparent;", edit_action_button_source)
        self.assertNotIn("width: 100%;", edit_action_button_source)
        self.assertIn("background: transparent;", edit_cancel_source)
        self.assertIn("border-color: oklch(98% 0.006 105 / 0.36);", edit_cancel_source)
        self.assertIn("background: var(--surface-strong);", edit_send_source)
        self.assertIn("color: var(--accent-ink);", edit_send_source)
        edit_textarea_source = styles_source.split(".message-bubble.user .message-edit-form textarea {", 1)[1].split(
            "}",
            1,
        )[0]
        edit_textarea_focus_source = styles_source.split(
            ".message-bubble.user .message-edit-form textarea:focus",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("outline: none;", edit_textarea_source)
        self.assertIn("box-shadow: none;", edit_textarea_source)
        self.assertIn("outline: none;", edit_textarea_focus_source)
        self.assertIn("box-shadow: none;", edit_textarea_focus_source)

    def test_attachment_only_user_messages_stay_visible_when_editing(self):
        app_source = self.source("frontend/src/App.tsx")
        panel_source = self.source("frontend/src/features/conversations/ConversationWorkspacePanel.tsx")
        draft_source = self.source("frontend/src/features/conversations/conversationDraft.ts")
        styles_source = self.source("frontend/src/styles.css")

        submit_source = app_source.split("async function submitEditedUserMessage", 1)[1].split(
            "async function showFavorite",
            1,
        )[0]
        self.assertIn("editingMessageContextResources", app_source)
        self.assertIn("editDraftFromMessage(message)", app_source)
        self.assertIn("setEditingMessageContextResources([])", app_source)
        self.assertIn("contextResources: message.context_resources ?? []", draft_source)
        self.assertIn("if (!hasSubmittableDraft(trimmedText, editingMessageContextResources))", submit_source)
        self.assertIn("contextResources: editingMessageContextResources", submit_source)
        self.assertNotIn("contextResources: message.context_resources ?? []", submit_source)
        self.assertNotIn("if (!trimmedText) {", submit_source)

        message_bubble_source = self.message_bubble_source()
        self.assertIn("const visibleContextResources = isEditingMessage ? editingMessageContextResources : message.context_resources ?? [];", message_bubble_source)
        self.assertIn("const hasVisibleMessageBody = Boolean(message.content || fileResources.length || quoteResources.length);", message_bubble_source)
        self.assertIn("message.role === \"assistant\" ? <span className=\"message-meta\">{emptyMessageText}</span> : null", message_bubble_source)

        message_edit_source = message_bubble_source.split("{isEditingMessage ? (", 1)[1].split(
            "</form>",
            1,
        )[0]
        self.assertIn('className="message-context-list message-edit-context-list"', message_edit_source)
        self.assertIn("fileResources.map((resource) => renderMessageFileReference(resource, {", message_edit_source)
        self.assertIn("onRemove: onRemoveEditingContextResource", message_edit_source)
        self.assertIn("onRemoveEditingContextResource={messageActions.removeEditingContextResource}", panel_source)
        self.assertIn("quoteResources.map((quote) => renderMessageQuoteReference(quote))", message_edit_source)
        self.assertNotIn('type="file"', message_edit_source)
        self.assertIn("function removeEditingContextResource", app_source)
        self.assertIn('aria-label={`移除附件：${resource.name}`}', app_source)
        self.assertIn('className="file-context-remove message-file-remove"', app_source)
        self.assertIn(".message-edit-context-list", styles_source)
        self.assertIn(".message-file-remove", styles_source)

    def test_chat_stream_keeps_latest_message_anchored_to_bottom(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("conversationSurfaceRef", app_source)
        self.assertIn("conversationTailKey", app_source)
        self.assertIn("function scrollConversationToLatest", app_source)
        self.assertIn("const surface = conversationSurfaceRef.current;", app_source)
        self.assertIn("surface.scrollTo({", app_source)
        self.assertIn("scrollLatestMessageIntoView(surface, behavior)", app_source)
        self.assertIn("latestMessage.getBoundingClientRect()", app_source)
        self.assertIn("currentComposerOverlayHeight(surface)", app_source)
        self.assertNotIn('className="conversation-tail-spacer"', app_source)
        self.assertNotIn(".conversation-tail-spacer", styles_source)
        self.assertIn(".message-list::after", styles_source)
        self.assertNotIn("conversationAtLatest", app_source)

    def test_streaming_does_not_force_scroll_after_user_browses_history(self):
        app_source = self.source("frontend/src/App.tsx")
        panel_source = self.source("frontend/src/features/conversations/ConversationWorkspacePanel.tsx")

        self.assertIn("shouldFollowConversationTailRef", app_source)
        self.assertIn("function isConversationNearTail(surface: HTMLDivElement)", app_source)
        self.assertIn("shouldFollowConversationTailRef.current = isConversationNearTail(surface);", app_source)
        self.assertIn("onConversationScroll={layout.updateConversationScrollState}", panel_source)

        scroll_effect_source = app_source.split("if (activeView !== \"home\"", 1)[1].split(
            "}, [activeScenario",
            1,
        )[0]
        self.assertIn("if (activeStreamTurnId && !shouldFollowConversationTailRef.current) {", scroll_effect_source)
        self.assertIn("return;", scroll_effect_source)
        self.assertIn("scrollConversationToLatest(activeStreamTurnId ? \"auto\" : \"smooth\")", scroll_effect_source)

    def test_composer_overlay_height_does_not_change_history_scroll_range(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("stage.style.setProperty(\"--composer-overlay-height\"", app_source)
        self.assertIn("composerRef", app_source)
        self.assertNotIn("--composer-clearance", styles_source)
        self.assertNotIn("composerClearance", app_source)
        self.assertNotIn("setComposerClearance", app_source)
        self.assertNotIn("homeWorkspaceStyle", app_source)
        self.assertNotIn("data-streaming={activeStreamTurnId", app_source)
        self.assertNotIn('.home-workspace[data-streaming="true"]', styles_source)
        self.assertNotIn("padding-bottom: var(--composer-overlay-height)", styles_source)
        self.assertIn(".message-list::after {\n  display: block;\n  height: var(--composer-overlay-height);", styles_source)
        self.assertNotIn("bottom: var(--composer-overlay-height)", styles_source)

    def test_composer_textarea_uses_internal_scroll_without_resizing_history(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")
        composer_source = app_source.split('className="assistant-composer conversation-composer"', 1)[1].split(
            "{composerError",
            1,
        )[0]
        resize_source = app_source.split("function resizeComposerTextarea()", 1)[1].split(
            "const childrenByParent",
            1,
        )[0]
        resize_effect_source = app_source.split("window.requestAnimationFrame(resizeComposerTextarea)", 1)[1].split(
            "]);",
            1,
        )[0]

        self.assertIn("composerTextareaRef", app_source)
        self.assertIn("resizeComposerTextarea", app_source)
        self.assertIn("composerText", resize_effect_source)
        self.assertIn("COMPOSER_TEXTAREA_MIN_HEIGHT_PX", app_source)
        self.assertIn("COMPOSER_TEXTAREA_MAX_HEIGHT_PX", app_source)
        self.assertIn('textarea.style.height = `${COMPOSER_TEXTAREA_MIN_HEIGHT_PX}px`;', resize_source)
        self.assertIn("const textareaBorderHeight = textarea.offsetHeight - textarea.clientHeight;", resize_source)
        self.assertIn("const nextHeight = Math.min(", resize_source)
        self.assertIn("COMPOSER_TEXTAREA_MAX_HEIGHT_PX", resize_source)
        self.assertIn(
            'textarea.style.overflowY = textarea.scrollHeight + textareaBorderHeight > COMPOSER_TEXTAREA_MAX_HEIGHT_PX ? "auto" : "hidden";',
            resize_source,
        )
        self.assertIn('ref={composerTextareaRef}', app_source)
        self.assertIn('ref={composerRef}', app_source)
        self.assertIn(".composer-input-frame", styles_source)
        self.assertIn("height: 24px;", styles_source)
        self.assertIn("min-height: 24px;", styles_source)
        self.assertIn("max-height: 144px;", styles_source)
        self.assertIn("font-size: var(--text-ui);", styles_source)
        self.assertIn("--conversation-copy-line-height: 20px;", styles_source)
        self.assertIn("line-height: var(--conversation-copy-line-height);", styles_source)
        self.assertIn("caret-color: var(--accent-ink);", styles_source)
        self.assertIn("overflow-y: hidden;", styles_source)
        self.assertIn("scrollbar-gutter: stable;", styles_source)
        self.assertNotIn("shouldKeepConversationAtLatest", resize_source)
        self.assertNotIn('scrollConversationToLatest("auto")', resize_source)
        self.assertIn('ref={composerTextareaRef}\n          rows={1}\n          value={composerText}', composer_source)
        self.assertLess(
            composer_source.index('className="composer-input-frame"'),
            composer_source.index('className="composer-footer"'),
        )
        self.assertNotIn("--composer-footer-space", styles_source)
        self.assertNotIn("padding: 0 2px var(--composer-footer-space) 0;", styles_source)
        footer_source = styles_source.split(".conversation-composer .composer-footer {", 1)[1].split("}", 1)[0]
        self.assertNotIn("position: absolute;", footer_source)
        self.assertNotIn("right: 0;", footer_source)
        self.assertNotIn("bottom: 0;", footer_source)
        self.assertNotIn("left: 0;", footer_source)

    def test_composer_textarea_keeps_text_flush_to_composer_content_edge_without_growing_initial_height(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")
        resize_source = app_source.split("function resizeComposerTextarea()", 1)[1].split(
            "const childrenByParent",
            1,
        )[0]
        marker = ".conversation-composer textarea {\n"
        self.assertIn(marker, styles_source)
        textarea_source = styles_source.split(marker, 1)[1].split("}", 1)[0]
        message_bubble_source = styles_source.rsplit(".message-bubble {\n  max-width: min(76%, 760px);", 1)[1].split("}", 1)[0]

        self.assertIn("height: 24px;", textarea_source)
        self.assertIn("min-height: 24px;", textarea_source)
        self.assertIn("font-size: var(--text-ui);", textarea_source)
        self.assertIn("line-height: var(--conversation-copy-line-height);", textarea_source)
        self.assertIn("line-height: var(--conversation-copy-line-height);", message_bubble_source)
        self.assertNotIn("--conversation-copy-line-height: 1.65;", styles_source)
        self.assertIn("border: 0;", textarea_source)
        self.assertIn("padding: 0;", textarea_source)
        self.assertNotIn("padding: 13px 12px;", textarea_source)
        self.assertIn("const textareaBorderHeight = textarea.offsetHeight - textarea.clientHeight;", resize_source)
        self.assertIn("textarea.scrollHeight + textareaBorderHeight", resize_source)
        self.assertNotIn("margin-top: -44px;", styles_source)
        self.assertNotIn("margin-top: -94px;", styles_source)

    def test_composer_does_not_show_suggested_prompt_buttons(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertNotIn("quick-prompts", app_source)
        self.assertNotIn("quick-prompts", styles_source)
        self.assertNotIn("快捷问题", app_source)
        self.assertNotIn("我这个症状需要马上去医院吗", app_source)
        self.assertNotIn("这个药可能有什么副作用", app_source)
        self.assertNotIn("我最近复查前应该注意什么", app_source)
        self.assertNotIn("seed?: string", app_source)

    def test_sidebar_account_button_opens_settings_page_directly(self):
        app_source = self.source("frontend/src/App.tsx")
        sidebar_source = self.source("frontend/src/app/Sidebar.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertNotIn("accountMenuOpen", app_source)
        self.assertNotIn("setAccountMenuOpen", app_source)
        self.assertIn('"account-button active" : "account-button"', sidebar_source)
        self.assertNotIn('aria-haspopup="menu"', sidebar_source)
        self.assertNotIn('className="account-menu"', sidebar_source)
        self.assertNotIn('role="menu"', sidebar_source)
        self.assertIn('aria-label="账号设置"', sidebar_source)
        self.assertIn("onNavigate(SETTING_PATH)", sidebar_source)
        self.assertIn(".account-button", styles_source)
        self.assertNotIn(".account-menu", styles_source)

    def test_workspace_continues_from_latest_assistant_by_default(self):
        app_source = self.source("frontend/src/App.tsx")

        self.assertIn("useState<string | null | undefined>(undefined)", app_source)
        self.assertIn("function latestAssistantMessageId()", app_source)
        self.assertIn("function nextParentMessageId()", app_source)
        self.assertIn("if (parentForNextMessage !== undefined)", app_source)
        self.assertIn("return latestAssistantMessageId()", app_source)
        self.assertIn("const parentMessageId = nextParentMessageId()", app_source)
        self.assertIn("parentMessageId,", app_source)
        self.assertNotIn("parentMessageId: parentForNextMessage,", app_source)
        self.assertNotIn("下一条消息将从选定历史节点分支。", app_source)

    def test_branch_selection_hides_later_history_and_can_restore_it(self):
        app_source = self.source("frontend/src/App.tsx")
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("const branchPreviewMessageIndex", app_source)
        self.assertIn("const visibleMessages = branchPreviewMessageIndex >= 0", app_source)
        self.assertIn("messages.slice(0, branchPreviewMessageIndex + 1)", app_source)
        self.assertIn("visibleMessages.map((message) => renderMessageBubble(message))", app_source)
        self.assertIn("function restoreBranchPreview()", app_source)
        self.assertIn("function renderBranchRestoreDivider()", app_source)
        self.assertIn("setParentForNextMessage(undefined)", app_source)
        self.assertIn("恢复分支前对话", app_source)
        self.assertIn('{showBranchRestoreDivider ? renderBranchRestoreDivider() : null}', app_source)
        self.assertIn(".branch-restore-divider", styles_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);", styles_source)
        self.assertIn(".branch-restore-divider::before", styles_source)
        self.assertIn(".branch-restore-divider::after", styles_source)

    def test_workspace_model_and_thinking_picker_uses_layered_popover(self):
        app_source = "\n".join(
            [
                self.source("frontend/src/App.tsx"),
                self.source("frontend/src/features/conversations/ComposerModelControl.tsx"),
            ]
        )
        styles_source = self.source("frontend/src/styles.css")

        self.assertIn("modelPickerOpen", app_source)
        self.assertNotIn("modelPickerPanel", app_source)
        self.assertIn("const composerModelControlRef = useRef<HTMLDivElement | null>(null);", app_source)
        self.assertIn("function closeModelPickerOnOutsidePointerDown(event: PointerEvent)", app_source)
        self.assertIn("document.addEventListener(\"pointerdown\", closeModelPickerOnOutsidePointerDown);", app_source)
        self.assertIn("document.removeEventListener(\"pointerdown\", closeModelPickerOnOutsidePointerDown);", app_source)
        self.assertIn("!control.contains(event.target as Node)", app_source)
        self.assertIn("function composerThinkingModeLabel", app_source)
        self.assertIn("function chooseThinkingMode", app_source)
        self.assertIn("function chooseSessionModel", app_source)
        self.assertNotIn("apiClient.setDefaultModel(modelId)", app_source)
        self.assertIn("apiClient.fetchModelDefaults()", app_source)
        self.assertIn("未添加聊天模型", app_source)
        self.assertNotIn("尚未添加默认聊天模型", app_source)
        self.assertNotIn("尚未添加模型", app_source)
        self.assertIn("setModelPickerOpen(false)", app_source)
        self.assertNotIn("setModelPickerPanel", app_source)
        self.assertIn('className="composer-model-control"', app_source)
        self.assertIn("controlRef={composerModelControlRef}", app_source)
        self.assertIn("ref={controlRef}", app_source)
        self.assertIn('className="composer-model-trigger"', app_source)
        self.assertIn('className="composer-model-popover"', app_source)
        self.assertIn('className="composer-model-popover-sections"', app_source)
        self.assertIn('className="composer-model-flyout composer-model-side-panel"', app_source)
        self.assertNotIn('className="composer-model-divider"', app_source)
        self.assertNotIn(">思考深度<", app_source)
        self.assertNotIn(">当前模型<", app_source)
        self.assertIn('default: "默认强度推理"', app_source)
        self.assertIn('fast: "关闭推理"', app_source)
        self.assertIn('low: "低强度推理"', app_source)
        self.assertIn('medium: "中强度推理"', app_source)
        self.assertIn('high: "高强度推理"', app_source)
        self.assertIn('xhigh: "超高强度推理"', app_source)
        self.assertIn('label === "关闭推理" ? "关闭" : label.replace(/强度推理$/, "")', app_source)
        self.assertIn("const currentThinkingLabel = composerThinkingModeLabel(thinkingMode);", app_source)
        self.assertIn("<span>{thinkingModeLabel(mode)}</span>", app_source)
        self.assertNotIn('default: "默认",', app_source)
        self.assertNotIn('fast: "速度",', app_source)
        self.assertNotIn('low: "低",', app_source)
        self.assertNotIn('medium: "中",', app_source)
        self.assertNotIn('high: "高",', app_source)
        self.assertNotIn('xhigh: "超高"', app_source)
        self.assertNotIn('default: "智能"', app_source)
        self.assertIn('aria-label="模型和推理强度"', app_source)
        self.assertNotIn('aria-label="模型和思考深度"', app_source)
        self.assertNotIn('aria-label="选择模型"', app_source)
        self.assertNotIn('aria-label="思考模式"', app_source)
        self.assertIn(".composer-model-control", styles_source)
        self.assertIn(".composer-model-popover", styles_source)
        self.assertIn(".composer-model-side-panel", styles_source)
        self.assertIn(".composer-model-flyout", styles_source)
        self.assertNotIn(".composer-model-divider", styles_source)
        self.assertNotIn("--composer-submit-offset", styles_source)
        self.assertIn(
            ".composer-model-popover {\n"
            "  position: absolute;\n"
            "  bottom: calc(100% + 10px);\n"
            "  left: 0;\n"
            "  z-index: 20;\n"
            "  display: grid;\n"
            "  width: max-content;",
            styles_source,
        )
        self.assertIn(".composer-model-popover-sections", styles_source)
        self.assertIn(
            ".composer-picker-section,\n"
            ".composer-thinking-options {\n"
            "  width: 100%;",
            styles_source,
        )
        self.assertIn(".composer-thinking-options {\n  justify-items: stretch;", styles_source)
        self.assertIn(
            ".composer-thinking-option,\n"
            ".composer-model-row {\n"
            "  width: 100%;",
            styles_source,
        )
        self.assertIn(
            ".conversation-composer .composer-model-control {\n"
            "  flex: 0 1 auto;\n"
            "  width: fit-content;",
            styles_source,
        )
        self.assertIn(
            ".conversation-composer .composer-model-trigger {\n"
            "  width: max-content;\n"
            "  max-width: 100%;",
            styles_source,
        )
        self.assertIn(
            ".conversation-composer .composer-model-popover {\n"
            "  position: fixed;\n"
            "  left: 14px;\n"
            "  right: 14px;",
            styles_source,
        )
        self.assertIn(
            ".composer-model-flyout {\n"
            "  position: absolute;\n"
            "  right: calc(100% + 8px);",
            styles_source,
        )
        self.assertIn(
            ".composer-model-row {\n"
            "  grid-template-columns: minmax(0, 1fr) auto;",
            styles_source,
        )
        self.assertIn(
            ".composer-thinking-option {\n"
            "  grid-template-columns: minmax(0, 1fr) auto;",
            styles_source,
        )
        self.assertNotIn("width: 232px;", styles_source)
        self.assertNotIn("width: min(300px, calc(100vw - 72px));", styles_source)
        self.assertNotIn(".composer-thinking-option,\n.composer-model-row {\n  width: max-content;", styles_source)
        self.assertNotIn('.composer-model-popover[data-panel="models"]', styles_source)
        self.assertNotIn("data-panel={modelPickerPanel}", app_source)
        self.assertNotIn("onClick={() => setThinkingMode(mode)}", app_source)

    def test_deepseek_model_picker_stays_content_sized_until_the_chat_column_is_too_narrow(self):
        styles_source = self.source("frontend/src/styles.css")

        narrow_deepseek_source = styles_source.split(
            "@media (max-width: 650px) {\n  .conversation-composer {",
            1,
        )[1].split(
            "\n}\n\n.conversation-surface",
            1,
        )[0]
        control_source = narrow_deepseek_source.split(".conversation-composer .composer-model-control {", 1)[1].split(
            "}",
            1,
        )[0]
        trigger_source = narrow_deepseek_source.split(".conversation-composer .composer-model-trigger {", 1)[1].split(
            "}",
            1,
        )[0]

        self.assertIn("width: fit-content;", control_source)
        self.assertIn("justify-self: end;", control_source)
        self.assertIn("max-width: min(520px, calc(var(--chat-column-width, 100vw) - 132px));", control_source)
        self.assertIn("width: max-content;", trigger_source)
        self.assertIn("max-width: 100%;", trigger_source)
        self.assertNotIn("\n    width: 100%;", control_source)
        self.assertNotIn("\n    width: 100%;", trigger_source)

    def test_frontend_docs_use_reasoning_strength_language(self):
        frontend_readme = self.source("frontend/README.md")
        frontend_design = self.source("docs/shared/frontend-design.md")
        docs_readme = self.source("docs/README.md")
        responsibilities = self.source("docs/shared/frontend-backend-responsibilities.md")
        roadmap = self.source("docs/roadmap.md")

        for source in (frontend_readme, frontend_design, docs_readme, responsibilities, roadmap):
            self.assertIn("推理强度", source)

        self.assertIn("模型与推理强度的组合选择器", frontend_readme)
        self.assertIn("推理强度列表", frontend_readme)
        self.assertIn("模型选择、推理强度、输入区模型弹层", frontend_readme)
        self.assertIn("主弹层把推理强度选项和当前模型值作为连续菜单项展示", frontend_readme)
        self.assertIn("触发按钮里的推理强度 chip 使用短文案", frontend_readme)
        self.assertIn("主弹层内推理强度选项和当前模型入口等宽", frontend_readme)
        self.assertIn("选择推理强度或模型后关闭", frontend_design)
        self.assertIn("触发按钮里的推理强度 chip 使用短文案", frontend_design)
        self.assertIn("主弹层内推理强度选项和当前模型入口等宽", frontend_design)
        self.assertIn("| 关闭推理 | `fast` |", frontend_design)
        self.assertIn("| 超高强度推理 | `xhigh` |", frontend_design)
        self.assertNotIn("| 速度 | `fast` |", frontend_design)
        self.assertNotIn("| 超高 | `xhigh` |", frontend_design)
        self.assertNotIn("思考深度", frontend_readme)
        self.assertNotIn("思考深度", frontend_design)
        self.assertNotIn("中间用分隔线区分", frontend_readme)

    def test_favorites_has_independent_page_route(self):
        app_source = self.source("frontend/src/App.tsx")
        routes_source = self.source("frontend/src/app/routes.ts")
        settings_source = self.source("frontend/src/features/settings/SettingsShell.tsx")
        sidebar_source = self.source("frontend/src/app/Sidebar.tsx")

        self.assertIn("typeof FAVORITES_PATH", routes_source)
        self.assertIn("window.location.pathname === FAVORITES_PATH", routes_source)
        self.assertIn("FavoritesWorkspacePanel", app_source)
        self.assertIn("route === FAVORITES_PATH", app_source)
        self.assertIn("onNavigate(FAVORITES_PATH)", sidebar_source)
        self.assertNotIn('activeView === "favorites"', app_source)
        self.assertNotIn('switchView("favorites")', app_source)

    def test_chat_session_route_opens_specific_conversation(self):
        app_source = self.source("frontend/src/App.tsx")
        routes_source = self.source("frontend/src/app/routes.ts")

        self.assertIn('CHAT_PATH_PREFIX = "/chat/"', routes_source)
        self.assertIn("function chatPathForSession(sessionId: string)", routes_source)
        self.assertIn("function sessionIdFromChatPath", routes_source)
        self.assertIn("window.location.pathname.startsWith(CHAT_PATH_PREFIX)", routes_source)
        self.assertIn("navigateTo(chatPathForSession(response.session_id)", app_source)
        self.assertIn("navigateTo(chatPathForSession(sessionId))", app_source)
        self.assertIn("const routeSessionId = sessionIdFromChatPath(route)", app_source)
        self.assertIn("await openConversation(routeSessionId)", app_source)

    def test_chat_switching_ignores_stale_conversation_detail_responses(self):
        app_source = self.source("frontend/src/App.tsx")

        open_conversation_source = app_source.split("async function openConversation", 1)[1].split(
            "async function openFavoriteSourceConversation",
            1,
        )[0]
        start_conversation_source = app_source.split("function startConversation", 1)[1].split(
            "function latestAssistantMessageId",
            1,
        )[0]
        reset_workspace_source = app_source.split("function resetWorkspaceState", 1)[1].split(
            "async function openConversation",
            1,
        )[0]

        self.assertIn("conversationRequestSeqRef", app_source)
        self.assertIn("const requestId = conversationRequestSeqRef.current + 1", open_conversation_source)
        self.assertIn("conversationRequestSeqRef.current = requestId", open_conversation_source)
        self.assertIn("if (requestId !== conversationRequestSeqRef.current)", open_conversation_source)
        self.assertLess(
            open_conversation_source.index("if (requestId !== conversationRequestSeqRef.current)"),
            open_conversation_source.index("setConversationDetail(detail)"),
        )
        self.assertIn("return false", open_conversation_source)
        self.assertIn("conversationRequestSeqRef.current += 1", start_conversation_source)
        self.assertIn("conversationRequestSeqRef.current += 1", reset_workspace_source)

    def test_chat_scrolls_to_latest_message_not_bottom_composer_spacer(self):
        app_source = self.source("frontend/src/App.tsx")
        scroll_latest_source = app_source.split("function scrollLatestMessageIntoView", 1)[1].split(
            "function scrollConversationToLatest",
            1,
        )[0]
        scroll_source = app_source.split("function scrollConversationToLatest", 1)[1].split(
            "function isConversationNearTail",
            1,
        )[0]

        self.assertIn("messageListRef", app_source)
        self.assertIn("LATEST_MESSAGE_MIN_VISIBLE_PX", app_source)
        self.assertIn("latestMessage.getBoundingClientRect()", scroll_latest_source)
        self.assertIn("surface.getBoundingClientRect()", scroll_latest_source)
        self.assertIn("currentComposerOverlayHeight(surface)", scroll_latest_source)
        self.assertIn("targetTop", scroll_latest_source)
        self.assertIn("surface.scrollTo({", scroll_latest_source)
        self.assertNotIn("latestMessage.scrollIntoView", scroll_latest_source)
        self.assertNotIn("top: surface.scrollHeight", scroll_source)

    def test_chat_opening_conversation_clears_stale_scroll_position_before_render(self):
        app_source = self.source("frontend/src/App.tsx")
        open_conversation_source = app_source.split("async function openConversation", 1)[1].split(
            "async function openFavoriteSourceConversation",
            1,
        )[0]

        self.assertIn("conversationSurfaceRef.current?.scrollTo({ top: 0, behavior: \"auto\" })", open_conversation_source)
        self.assertLess(
            open_conversation_source.index("conversationSurfaceRef.current?.scrollTo"),
            open_conversation_source.index("setConversationDetail(detail)"),
        )

    def test_chat_history_switch_resets_scroll_and_does_not_autoscroll_to_bottom_spacer(self):
        app_source = self.source("frontend/src/App.tsx")

        self.assertIn("useLayoutEffect", app_source)
        self.assertIn("lastRenderedConversationSessionRef", app_source)
        self.assertIn("autoScrollConversationSessionRef", app_source)
        self.assertIn('scrollConversationToLatest("auto")', app_source)
        self.assertIn("conversationSessionId: conversationDetail?.session_id ?? null", app_source)
        self.assertIn("const sessionChanged = autoScrollConversationSessionRef.current !== conversationSessionId", app_source)
        self.assertIn("if (sessionChanged && !activeStreamTurnId) {", app_source)

    def test_favorites_and_setting_pages_share_main_workspace_sidebar(self):
        app_source = self.source("frontend/src/App.tsx")
        sidebar_source = self.source("frontend/src/app/Sidebar.tsx")

        self.assertIn("function renderWorkspaceShell(", app_source)
        self.assertIn("PatientShell", app_source)
        self.assertIn("function Sidebar(", sidebar_source)
        self.assertIn("FavoritesWorkspacePanel", app_source)
        self.assertIn("SettingsWorkspacePanel", app_source)
        self.assertIn('"account-button active" : "account-button"', sidebar_source)
        self.assertNotIn('className="account-menu"', sidebar_source)
        self.assertIn("onNavigate(SETTING_PATH)", sidebar_source)
        self.assertIn('className={route === FAVORITES_PATH ? "nav-item active" : "nav-item"}', sidebar_source)
        self.assertNotIn('className="page-shell settings-page"', app_source)
        self.assertNotIn('className="page-shell favorites-page"', app_source)
        self.assertNotIn("route === SETTINGS_PATH", app_source)

    def test_logout_clears_previous_user_workspace_state(self):
        app_source = self.source("frontend/src/App.tsx")
        settings_source = self.source("frontend/src/features/settings/SettingsShell.tsx")

        self.assertIn("function resetWorkspaceState()", app_source)
        self.assertIn("resetWorkspaceState();", app_source)
        self.assertIn("退出登录", settings_source)
        self.assertNotIn("Sign out", app_source)
        for reset_call in (
            'setConversationDetail(null)',
            'setConversations([])',
            'setFavorites([])',
            'setSelectedFavoriteIds([])',
            'setFavoriteDetail(null)',
            'setModels([])',
            'setSelectedModelId("")',
            'setUploadedResources([])',
            'setComposerText("")',
            'setComposerError("")',
        ):
            self.assertIn(reset_call, app_source)

    def test_request_client_explains_browser_network_failures(self):
        request_source = (self.root / "frontend" / "src" / "api" / "request.ts").read_text(
            encoding="utf-8"
        )
        vite_config_source = (self.root / "frontend" / "vite.config.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("networkFailureMessage", request_source)
        self.assertIn("无法连接后端服务", request_source)
        self.assertIn('?? "/api"', request_source)
        self.assertNotIn('?? "http://127.0.0.1:8000/api"', request_source)
        self.assertIn("Vite 代理到 http://127.0.0.1:8000", request_source)
        self.assertIn("当前页面地址", request_source)
        self.assertIn("proxy", vite_config_source)
        self.assertIn('"/api"', vite_config_source)
        self.assertIn('"http://127.0.0.1:8000"', vite_config_source)

    def test_docs_name_setting_and_favorites_page_routes(self):
        prd_index = (self.root / "docs" / "releases" / "v0.1.0" / "prd" / "README.md").read_text(
            encoding="utf-8"
        )
        account_settings_prd = (
            self.root / "docs" / "releases" / "v0.1.0" / "prd" / "account-settings.md"
        ).read_text(encoding="utf-8")
        favorites_prd = (
            self.root / "docs" / "releases" / "v0.1.0" / "prd" / "favorites.md"
        ).read_text(encoding="utf-8")

        self.assertIn("账号设置页 `/setting`", prd_index)
        self.assertIn("患者主工作台 `/`", prd_index)
        self.assertIn("我的收藏页 `/favorites`", prd_index)
        self.assertIn("左侧主工作栏在 `/`、`/favorites` 和 `/setting` 均保持存在", prd_index)
        self.assertNotIn("`/app`", prd_index)
        self.assertIn("账号设置从左下角账号按钮直接进入 `/setting` 页面", account_settings_prd)
        self.assertIn("左侧全局导航中的 `我的收藏`，进入 `/favorites`", favorites_prd)

    def test_frontend_design_doc_records_current_workspace_decisions(self):
        frontend_design = (self.root / "docs" / "shared" / "frontend-design.md").read_text(encoding="utf-8")
        frontend_readme = (self.root / "frontend" / "README.md").read_text(encoding="utf-8")

        for expected in (
            "品牌区只展示 `Serenita`",
            "左侧导航支持折叠",
            "左侧导航和右侧主页之间只使用一条竖向分隔线",
            "会话标题限制在左侧导航栏内部",
            "`原始文件` 排在 `我的收藏` 上方，并固定在账号按钮上方的底部辅助区",
            "会话列表不显示 `最近会话` 或 `最近对话` 标题",
            "会话删除按钮使用悬浮垃圾桶图标",
            "左下角账号按钮",
            "账号设置",
            "退出登录",
            "`报告`、`生活` 场景入口位于左侧栏；首页工作区顶部不再放置居中场景入口",
            "对话过程中主标题显示当前会话标题",
            "输入区不展示快捷问题或示例提问按钮",
            "输入输出内容使用 Markdown 渲染",
            "思考过程以可折叠区域显示",
            "对话历史滚动条属于整块会话区域",
            "输入框浮在会话历史上方",
            "最新生成过程、最新回答和最新历史记录自动显示在输入框上方",
            "输入框默认保持较矮高度",
            "输入框随输入行数逐步增高，到达阈值后改为输入框内部滚动",
            "输入框行数变化不得改变对话历史滚动容器的高度、滚动范围或滚动条位置",
            "对话历史列和悬浮输入框必须使用同一条居中列宽和响应式左右留白",
            "不得使用固定像素 inset 或 JS offset 硬凑",
            "滚动条预留空间不得造成历史列与输入框左右错位",
            "`conversation-surface`、`message-list` 和 `conversation-composer` 的关系",
            "更新输入框高度只允许更新 `--composer-overlay-height`",
            "所有行的输入光标高度必须一致，并与文字字号和行高一致",
            "悬浮输入框不使用发光阴影",
            "不受全局按钮 hover 位移影响",
        ):
            self.assertIn(expected, frontend_design)

        for expected in (
            "`patient-main:has(.home-workspace)` 会把首页右侧主区 padding 归零",
            "`--chat-scrollbar-gutter`、`--chat-column-side-gap` 计算 `--chat-column-width`",
            "`overflow-y: auto`",
            "`scrollbar-gutter: stable`",
            "定义克制但可见的 scrollbar thumb",
            "不能使用 `stable both-edges`",
            "`--chat-scrollbar-axis-offset`",
            "`home-workspace-content` 是会话舞台和悬浮输入区定位容器",
            "`conversation-surface` 是唯一历史滚动容器",
            "`message-list` 只负责列宽和尾部留白",
            "普通消息容器不再依赖黑色 1px 边框",
        ):
            self.assertIn(expected, frontend_readme)

        expected_readme_order = (
            "## 前端概览",
            "## 本地开发",
            "## 页面与路由总览",
            "## 登录与注册模块",
            "## 共享应用外壳",
            "## 主工作台模块",
            "## 账号设置模块",
            "## 我的收藏模块",
            "## 共享实现细节",
            "## 视觉与布局系统",
            "## 当前边界与后续拆分方向",
        )
        previous_index = -1
        for heading in expected_readme_order:
            current_index = frontend_readme.index(heading)
            self.assertGreater(current_index, previous_index)
            previous_index = current_index

    def test_frontend_readme_records_current_reorganization_outcome(self):
        frontend_readme = (self.root / "frontend" / "README.md").read_text(encoding="utf-8")

        for expected in (
            "`App.tsx` 现在只保留应用入口职责",
            "`features/conversations/useWorkspacePageModel.ts`",
            "`features/conversations/WorkspaceRouteContent.tsx`",
            "`features/conversations/ConversationWorkspacePanel.tsx`",
            "`features/favorites/FavoritesWorkspacePanel.tsx`",
            "`features/settings/SettingsWorkspacePanel.tsx`",
            "`styles.css` 只作为兼容入口引入 `src/styles/index.css`",
            "`base.css` 只保留 reset、body、原生表单和全局 focus",
            "跨页面复用的 Markdown、SecretInput、状态文本和共享按钮放在 `components.css`",
        ):
            self.assertIn(expected, frontend_readme)

    def test_frontend_design_doc_records_current_reorganization_outcome(self):
        design_doc = (self.root / "docs" / "shared" / "frontend-design.md").read_text(encoding="utf-8")

        for expected in (
            "当前代码入口 `frontend/src/App.tsx` 只负责路由和认证门禁",
            "登录后工作台页入口由 `features/conversations/WorkspacePage.tsx` 承担",
            "右侧工作区和会话状态编排由 `features/conversations/useWorkspacePageModel.ts` 承担",
            "登录后 route 分支和 `WorkspaceRouteShell` 包装由 `features/conversations/WorkspaceRouteContent.tsx` 承担",
            "收藏页工作区外壳由 `FavoritesWorkspacePanel` 承担",
            "账号设置工作区外壳由 `SettingsWorkspacePanel` 承担",
            "样式入口 `frontend/src/styles.css` 只保留一行 `@import \"./styles/index.css\";`",
            "`base.css` 只保留 reset、body、原生表单和全局 focus",
        ):
            self.assertIn(expected, design_doc)

        self.assertNotIn("docs/superpowers", design_doc)

    def test_frontend_backend_responsibilities_doc_records_split_frontend(self):
        responsibilities_doc = (
            self.root / "docs" / "shared" / "frontend-backend-responsibilities.md"
        ).read_text(encoding="utf-8")

        for expected in (
            "| `frontend/src/App.tsx` | 顶层 session 恢复、路由保护和页面拼装 |",
            "| `frontend/src/app/` | 患者工作台外壳、侧栏、浏览器路由 helper 和响应式侧栏状态 |",
            "| `frontend/src/features/auth/` | 登录、注册、会话恢复和退出 |",
            "| `frontend/src/features/conversations/` | 首页对话、侧栏场景入口、消息、输入区、流式生成、附件、引用和分支 |",
            "| `frontend/src/features/favorites/` | 收藏列表、详情、标签编辑和批量操作 |",
            "| `frontend/src/features/settings/` | 账号资料、密码安全、模型提供方、默认模型和模型管理 |",
            "| `frontend/src/styles/` | 样式 token、基础样式、外壳、各 feature 样式和响应式规则 |",
        ):
            self.assertIn(expected, responsibilities_doc)

        self.assertNotIn("患者工作台主体、路由、对话、收藏、侧边栏和大量交互状态", responsibilities_doc)
        self.assertNotIn("App.tsx` 很大", responsibilities_doc)

    def test_frontend_architecture_target_folders_exist(self):
        expected_dirs = [
            "frontend/src/app",
            "frontend/src/features/auth",
            "frontend/src/features/conversations",
            "frontend/src/features/favorites",
            "frontend/src/features/settings",
            "frontend/src/components",
            "frontend/src/styles",
        ]
        for expected_dir in expected_dirs:
            self.assertTrue((self.root / expected_dir).is_dir(), expected_dir)

    def test_app_tsx_is_a_thin_route_shell_after_reorganization(self):
        app_source = self.source("frontend/src/App.tsx")
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        route_content_source = self.source("frontend/src/features/conversations/WorkspaceRouteContent.tsx")
        self.assertIn("useAuthSession", app_source)
        self.assertIn("useBrowserRoute", app_source)
        self.assertIn("PatientShell", app_source)
        self.assertIn("AuthPage", app_source)
        self.assertIn("WorkspacePage", app_source)
        self.assertIn("WorkspaceRouteContent", workspace_source)
        self.assertIn("FavoritesWorkspacePanel", route_content_source)
        self.assertIn("SettingsWorkspacePanel", route_content_source)
        for moved_name in [
            "renderLoginPage",
            "renderMainWorkspace",
            "renderFavoritesWorkspace",
            "renderComposerModelControl",
            "renderMessageBubble",
            "renderSidebar",
            "submitAuth",
            "sendMessage",
            "toggleFavorite",
            "batchDeleteFavorites",
        ]:
            self.assertNotIn(moved_name, app_source)
        self.assertLessEqual(len(app_source.splitlines()), 300)

    def test_route_helpers_live_under_app_routes(self):
        routes_source = self.source("frontend/src/app/routes.ts")
        app_source = self.source("frontend/src/App.tsx")

        for expected in [
            'SIGN_IN_PATH = "/sign_in"',
            'SIGN_UP_PATH = "/sign_up"',
            'APP_PATH = "/"',
            'FAVORITES_PATH = "/favorites"',
            'SETTING_PATH = "/setting"',
            'CHAT_PATH_PREFIX = "/chat/"',
            "function currentRoute",
            "function chatPathForSession",
            "function sessionIdFromChatPath",
            "function isAuthRoute",
        ]:
            self.assertIn(expected, routes_source)

        self.assertNotIn("function currentRoute", app_source)
        self.assertNotIn("function sessionIdFromChatPath", app_source)
        self.assertNotIn('const SIGN_IN_PATH = "/sign_in"', app_source)

    def test_patient_shell_owns_sidebar_responsive_state(self):
        hook_source = self.source("frontend/src/app/useResponsiveSidebar.ts")
        shell_source = self.source("frontend/src/app/PatientShell.tsx")
        sidebar_source = self.source("frontend/src/app/Sidebar.tsx")

        self.assertIn('SIDEBAR_COMPACT_MEDIA = "(max-width: 1000px)"', hook_source)
        self.assertIn("mobileSidebarOpen", hook_source)
        self.assertIn("sidebarCollapsed", hook_source)
        self.assertIn("compactSidebarMode", hook_source)
        self.assertIn('data-mobile-sidebar-open={mobileSidebarOpen ? "true" : "false"}', shell_source)
        self.assertIn('data-sidebar-collapsed={sidebarCollapsed ? "true" : "false"}', shell_source)
        self.assertIn('className="mobile-sidebar-backdrop"', shell_source)
        self.assertIn('className="patient-sidebar"', sidebar_source)
        self.assertIn('aria-label="主导航"', sidebar_source)

    def test_workspace_route_shell_owns_sidebar_toggle_controller(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        route_shell_source = self.source("frontend/src/app/WorkspaceRouteShell.tsx")
        route_content_source = self.source("frontend/src/features/conversations/WorkspaceRouteContent.tsx")
        page_model_source = self.source("frontend/src/features/conversations/useWorkspacePageModel.ts")

        self.assertIn("export function useWorkspaceRouteShell", route_shell_source)
        self.assertIn("export function WorkspaceRouteShell", route_shell_source)
        self.assertIn("useResponsiveSidebar", route_shell_source)
        self.assertIn("function renderSidebarToggle", route_shell_source)
        self.assertIn("const showWorkspaceSidebarToggle = compactSidebarMode ? !mobileSidebarOpen : sidebarCollapsed;", route_shell_source)
        self.assertIn("<ShellComponent", route_shell_source)
        self.assertIn("sidebarCollapsed={shellControls.sidebarCollapsed}", route_shell_source)
        self.assertIn("const workspaceShell = useWorkspaceRouteShell()", page_model_source)
        self.assertIn("workspaceShell", page_model_source)
        self.assertNotIn("useWorkspaceRouteShell", workspace_source)
        self.assertIn("shellControls={workspaceShell}", route_content_source)
        self.assertIn("workspaceShell.renderSidebarToggle", route_content_source)
        self.assertNotIn("useResponsiveSidebar", workspace_source)
        self.assertNotIn("SidebarToggleIcon", workspace_source)
        self.assertNotIn("function renderSidebarToggle", workspace_source)
        self.assertNotIn("const [accountMenuOpen", workspace_source)

    def test_workspace_sidebar_open_button_uses_settings_style_back_icon(self):
        route_shell_source = self.source("frontend/src/app/WorkspaceRouteShell.tsx")
        sidebar_source = self.source("frontend/src/app/Sidebar.tsx")
        icons_source = self.source("frontend/src/components/icons.tsx")

        toggle_source = route_shell_source.split("function renderSidebarToggle", 1)[1].split(
            "return {",
            1,
        )[0]

        self.assertIn("SidebarBackIcon", icons_source)
        self.assertIn("sidebar-back-icon", icons_source)
        self.assertIn('strokeWidth="2.4"', icons_source)
        self.assertIn("SidebarBackIcon", route_shell_source)
        self.assertIn("<SidebarBackIcon />", toggle_source)
        self.assertNotIn("SidebarToggleIcon", toggle_source)
        self.assertIn("<SidebarCloseIcon />", sidebar_source)
        self.assertNotIn("<SidebarToggleIcon", sidebar_source)

    def test_auth_conversation_favorites_settings_own_local_state(self):
        auth_source = self.source("frontend/src/features/auth/AuthPage.tsx")
        session_source = self.source("frontend/src/features/auth/useAuthSession.ts")
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        page_model_source = self.source("frontend/src/features/conversations/useWorkspacePageModel.ts")
        conversation_surface_source = self.source(
            "frontend/src/features/conversations/ConversationWorkspaceSurface.tsx"
        )
        conversation_workspace_source = self.source("frontend/src/features/conversations/useConversationWorkspace.ts")
        conversation_stream_source = self.source("frontend/src/features/conversations/useConversationStreamController.ts")
        favorites_source = self.source("frontend/src/features/favorites/FavoritesWorkspace.tsx")
        favorite_workspace_source = self.source("frontend/src/features/favorites/useFavoriteWorkspace.ts")
        settings_source = self.source("frontend/src/features/settings/SettingsShell.tsx")

        self.assertIn("submitAuth", auth_source)
        self.assertIn("SecretInput", auth_source)
        self.assertIn("authenticate", session_source)
        self.assertIn("signOut", session_source)

        for expected in ["renderMainWorkspace", "renderMessageBubble", "renderComposerModelControl"]:
            self.assertIn(expected, conversation_surface_source)
            self.assertNotIn(expected, workspace_source)
        for expected in ["openConversation"]:
            self.assertIn(expected, page_model_source)
        for expected in [
            "async function sendMessage",
            "async function submitConversationMessage",
            "async function regenerate",
        ]:
            self.assertIn(expected, conversation_workspace_source)
            self.assertNotIn(expected, workspace_source)
        self.assertIn("async function cancelActiveGeneration", conversation_stream_source)
        self.assertNotIn("async function cancelActiveGeneration", conversation_workspace_source)

        self.assertIn('className="favorite-list"', favorites_source)
        self.assertIn('className="favorite-detail"', favorites_source)
        for expected in ["showFavorite", "batchDeleteFavorites", "flushFavoriteTags"]:
            self.assertIn(expected, favorite_workspace_source)

        self.assertIn("activeSection", settings_source)
        self.assertIn("provider-panel", settings_source)
        self.assertIn("providers.map", settings_source)

    def test_favorite_workspace_state_moves_into_dedicated_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        favorite_workspace_source = self.source("frontend/src/features/favorites/useFavoriteWorkspace.ts")

        for expected in [
            "async function showFavorite",
            "function closeFavoriteDetail",
            "async function batchDeleteFavorites",
            "async function flushFavoriteTags",
            "function toggleFavoriteSelectionMode",
            "function toggleFavoriteTagEditor",
        ]:
            self.assertIn(expected, favorite_workspace_source)
            self.assertNotIn(expected, workspace_source)

    def test_favorite_list_alignment_moves_into_dedicated_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        page_model_source = self.source("frontend/src/features/conversations/useWorkspacePageModel.ts")
        favorite_list_alignment_source = self.source("frontend/src/features/favorites/useFavoriteListAlignment.ts")

        self.assertIn("export function useFavoriteListAlignment", favorite_list_alignment_source)
        self.assertIn("useFavoriteListAlignment({", page_model_source)
        self.assertNotIn("useFavoriteListAlignment", workspace_source)
        for expected in [
            "function updateFavoriteListAlignment",
            "new ResizeObserver",
            "list.offsetWidth - list.clientWidth - listHorizontalBorderWidth",
            '"--favorite-list-end-compensation"',
        ]:
            self.assertIn(expected, favorite_list_alignment_source)
            self.assertNotIn(expected, workspace_source)

    def test_favorite_message_actions_move_into_dedicated_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        page_model_source = self.source("frontend/src/features/conversations/useWorkspacePageModel.ts")
        favorite_message_actions_source = self.source("frontend/src/features/favorites/useFavoriteMessageActions.ts")

        self.assertIn("export function useFavoriteMessageActions", favorite_message_actions_source)
        self.assertIn("useFavoriteMessageActions({", page_model_source)
        self.assertNotIn("useFavoriteMessageActions", workspace_source)
        for expected in [
            "async function toggleFavorite",
            "apiClient.deleteFavorite(existing.favorite_id)",
            "apiClient.createFavorite(currentSessionId, message.message_id, [])",
            "apiClient.fetchFavorites()",
        ]:
            self.assertIn(expected, favorite_message_actions_source)
            self.assertNotIn(expected, workspace_source)

    def test_favorites_workspace_wrapper_moves_into_favorites_feature(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        route_content_source = self.source("frontend/src/features/conversations/WorkspaceRouteContent.tsx")
        favorite_panel_source = self.source("frontend/src/features/favorites/FavoritesWorkspacePanel.tsx")

        self.assertIn("export function FavoritesWorkspacePanel", favorite_panel_source)
        self.assertIn("favoriteWorkspace={favoriteWorkspace}", route_content_source)
        self.assertNotIn("function renderFavoritesWorkspace()", workspace_source)
        for expected in [
            "FavoritesWorkspace",
            "favoriteWorkspace.addingFavoriteTagId",
            "favoriteWorkspace.favoriteDetailAutoSaveRef",
            "favoriteWorkspace.setSelectedFavoriteIds",
            "void onOpenConversation(sessionId, sourceMessageId)",
        ]:
            self.assertIn(expected, favorite_panel_source)
        for moved_prop in [
            "beginBatchTagEditing={beginBatchTagEditing}",
            "favoriteDetailAutoSaveRef={favoriteDetailAutoSaveRef}",
            "favoriteListPanelRef={favoriteListPanelRef}",
            "toggleFavoriteSelectionMode={toggleFavoriteSelectionMode}",
        ]:
            self.assertNotIn(moved_prop, workspace_source)

    def test_settings_workspace_wrapper_moves_into_settings_feature(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        settings_workspace_source = self.source("frontend/src/features/settings/SettingsWorkspacePanel.tsx")

        self.assertIn("export function SettingsWorkspacePanel", settings_workspace_source)
        for expected in [
            'className="workspace-panel settings-workspace"',
            'className="settings-toolbar"',
            "SettingsShell",
            "apiClient.fetchModels()",
            "onModelsChanged(mergeModelsWithChatDefault(",
        ]:
            self.assertIn(expected, settings_workspace_source)
            self.assertNotIn(expected, workspace_source)

    def test_conversation_workspace_actions_move_into_dedicated_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        conversation_workspace_source = self.source("frontend/src/features/conversations/useConversationWorkspace.ts")

        for expected in [
            "async function sendMessage",
            "async function submitConversationMessage",
            "async function regenerate",
        ]:
            self.assertIn(expected, conversation_workspace_source)
            self.assertNotIn(expected, workspace_source)

    def test_conversation_stream_control_moves_into_dedicated_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        conversation_workspace_source = self.source("frontend/src/features/conversations/useConversationWorkspace.ts")
        stream_controller_source = self.source(
            "frontend/src/features/conversations/useConversationStreamController.ts"
        )

        self.assertIn("export function useConversationStreamController", stream_controller_source)
        self.assertIn("useConversationStreamController({", conversation_workspace_source)
        for expected in [
            "async function startResponseStream",
            "async function cancelActiveGeneration",
            "function finishActiveStream",
            "function currentStreamingContent",
            "apiClient.streamConversation",
            "apiClient.cancelTurn",
            "AbortController",
            'if (event.event === "cancelled")',
            'if (event.event === "failed")',
        ]:
            self.assertIn(expected, stream_controller_source)
            self.assertNotIn(expected, conversation_workspace_source)
            self.assertNotIn(expected, workspace_source)

    def test_conversation_workspace_panel_owns_surface_prop_mapping(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        panel_source = self.source("frontend/src/features/conversations/ConversationWorkspacePanel.tsx")
        route_content_source = self.source("frontend/src/features/conversations/WorkspaceRouteContent.tsx")

        self.assertIn("export function ConversationWorkspacePanel", panel_source)
        self.assertIn("ConversationWorkspacePanel", route_content_source)
        self.assertIn("<ConversationWorkspaceSurface", panel_source)
        self.assertIn("pageState", panel_source)
        self.assertIn("modelControl", panel_source)
        self.assertIn("viewState", panel_source)
        self.assertIn("workspaceActions", panel_source)
        self.assertIn("messageActions", panel_source)
        self.assertIn("branching", panel_source)
        self.assertIn("attachments", panel_source)
        self.assertNotIn("ConversationWorkspaceSurface", workspace_source)
        self.assertNotIn("<ConversationWorkspaceSurface", workspace_source)
        self.assertNotIn("onCancelActiveGeneration={() =>", workspace_source)
        self.assertNotIn("onSubmitEditedUserMessage={submitEditedUserMessage}", workspace_source)

    def test_workspace_route_content_owns_shell_and_route_rendering(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        route_content_source = self.source("frontend/src/features/conversations/WorkspaceRouteContent.tsx")

        self.assertIn("export function WorkspaceRouteContent", route_content_source)
        self.assertIn("WorkspaceRouteContent", workspace_source)
        for expected in [
            "function renderWorkspaceShell(",
            "function renderAppPage(",
            "function renderRoute(",
            "<WorkspaceRouteShell",
            "ConversationWorkspacePanel",
            "FavoritesWorkspacePanel",
            "SettingsWorkspacePanel",
            "if (route === FAVORITES_PATH)",
            "if (route === SETTING_PATH)",
            "if (route === APP_PATH)",
        ]:
            self.assertIn(expected, route_content_source)
            self.assertNotIn(expected, workspace_source)

    def test_workspace_page_model_owns_workspace_hook_composition(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        page_model_source = self.source("frontend/src/features/conversations/useWorkspacePageModel.ts")

        self.assertIn("export function useWorkspacePageModel", page_model_source)
        self.assertIn("useWorkspacePageModel({", workspace_source)
        self.assertIn("<WorkspaceRouteContent", workspace_source)
        for expected in [
            "useWorkspaceRouteShell()",
            "useConversationPageState()",
            "useConversationModelControl({",
            "useConversationViewState({",
            "useConversationLayout({",
            "useFavoriteWorkspace({",
            "useFavoriteListAlignment({",
            "useFavoriteMessageActions({",
            "useConversationLifecycle({",
            "useConversationWorkspace({",
            "useConversationMessageActions({",
            "useConversationBranching({",
            "useConversationAttachments({",
        ]:
            self.assertIn(expected, page_model_source)
            self.assertNotIn(expected, workspace_source)
        self.assertNotIn("const {", workspace_source)
        self.assertNotIn("setComposerError", workspace_source)

    def test_conversation_message_actions_move_into_dedicated_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        message_actions_source = self.source("frontend/src/features/conversations/useConversationMessageActions.ts")

        for expected in [
            "async function copyMessage",
            "function updateQuoteSelection",
            "function addSelectedTextToConversation",
            "function editUserMessage",
            "async function submitEditedUserMessage",
        ]:
            self.assertIn(expected, message_actions_source)
            self.assertNotIn(expected, workspace_source)

    def test_conversation_branching_actions_move_into_dedicated_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        branching_source = self.source("frontend/src/features/conversations/useConversationBranching.ts")

        for expected in [
            "async function switchBranch",
            "function branchParentKey",
            "function branchAfter",
            "function restoreBranchPreview",
        ]:
            self.assertIn(expected, branching_source)
            self.assertNotIn(expected, workspace_source)

    def test_conversation_attachment_actions_move_into_dedicated_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        attachments_source = self.source("frontend/src/features/conversations/useConversationAttachments.ts")

        for expected in [
            "async function handleFileUpload",
            "function removeUploadedResource",
        ]:
            self.assertIn(expected, attachments_source)
            self.assertNotIn(expected, workspace_source)
        self.assertIn("apiClient.uploadContextResource", attachments_source)

    def test_attachment_resource_filtering_moves_into_attachments_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        page_model_source = self.source("frontend/src/features/conversations/useWorkspacePageModel.ts")
        attachments_source = self.source("frontend/src/features/conversations/useConversationAttachments.ts")

        self.assertIn("filterResourcesByMimeTypes(current, selectedModelFileMimeTypes)", attachments_source)
        self.assertIn("selectedModelFileMimeTypes", attachments_source)
        self.assertIn("uploadedResourcesLength", attachments_source)
        self.assertIn("selectedModelFileMimeTypes,", page_model_source)
        self.assertIn("uploadedResourcesLength: uploadedResources.length", page_model_source)
        self.assertNotIn("filterResourcesByMimeTypes(current, selectedModelFileMimeTypes)", workspace_source)

    def test_conversation_view_state_moves_derived_values_into_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        page_model_source = self.source("frontend/src/features/conversations/useWorkspacePageModel.ts")
        view_state_source = self.source("frontend/src/features/conversations/useConversationViewState.ts")
        attachment_support_source = self.source("frontend/src/features/conversations/attachmentSupport.ts")

        self.assertIn("export function useConversationViewState", view_state_source)
        self.assertIn("useConversationViewState({", page_model_source)
        self.assertIn("visionParseModel,", page_model_source)
        self.assertIn("visionParseModel", view_state_source)
        self.assertIn("export function mergeModelFileMimeTypes", attachment_support_source)
        self.assertNotIn("useConversationViewState", workspace_source)
        for expected in [
            "const selectedScenario = scenarioCopy[activeScenario]",
            'const workspaceTitle = activeScenario === "home" && conversationDetail ? conversationDetail.title : selectedScenario.title',
            "const selectedModelFileMimeTypes = mergeModelFileMimeTypes(selectedModel, visionParseModel)",
            "const canAttachFiles = canAttachFilesForScenario(activeScenario, selectedModelFileMimeTypes)",
            "const messagesById = useMemo(() => createMessageIndex(allMessages), [allMessages])",
            "const branchPreviewMessageIndex",
            "const visibleMessages = branchPreviewMessageIndex >= 0",
            "const showBranchRestoreDivider = branchPreviewMessageIndex >= 0",
        ]:
            self.assertIn(expected, view_state_source)
            self.assertNotIn(expected, workspace_source)
        for imported_helper in [
            "canAttachFilesForScenario",
            "mergeModelFileMimeTypes",
            "createMessageIndex",
            "scenarioCopy",
        ]:
            self.assertNotIn(f'import {{ {imported_helper}', workspace_source)
        self.assertNotIn("useMemo", workspace_source)

    def test_conversation_page_state_moves_state_and_refs_into_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        page_model_source = self.source("frontend/src/features/conversations/useWorkspacePageModel.ts")
        page_state_source = self.source("frontend/src/features/conversations/useConversationPageState.ts")

        self.assertIn("export function useConversationPageState", page_state_source)
        self.assertIn("useConversationPageState()", page_model_source)
        self.assertNotIn("useConversationPageState", workspace_source)
        for expected in [
            'const [activeView, setActiveView] = useState<WorkspaceView>("home")',
            'const [activeScenario, setActiveScenario] = useState<ScenarioTab>("home")',
            'const [composerText, setComposerText] = useState("")',
            "const [conversationDetail, setConversationDetail] = useState<ConversationDetail | null>(null)",
            "const [conversations, setConversations] = useState<ConversationSummary[]>([])",
            "const [visionParseModel, setVisionParseModel] = useState<AddedModel | null>(null)",
            "const [uploadedResources, setUploadedResources] = useState<UploadedResource[]>([])",
            "const [parentForNextMessage, setParentForNextMessage] = useState<string | null | undefined>(undefined)",
            "const [editingMessageContextResources, setEditingMessageContextResources] = useState<Array<Record<string, unknown>>>([])",
            "const messageRefs = useRef(new Map<string, HTMLElement>())",
            "const activeStreamRef = useRef<ActiveStream | null>(null)",
            "const conversationRequestSeqRef = useRef(0)",
        ]:
            self.assertIn(expected, page_state_source)
            self.assertNotIn(expected, workspace_source)
        self.assertNotIn("useState", workspace_source)
        self.assertNotIn("useRef", workspace_source)

    def test_conversation_workspace_owns_conversation_list_refresh(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        conversation_workspace_source = self.source("frontend/src/features/conversations/useConversationWorkspace.ts")

        self.assertNotIn("apiClient", workspace_source)
        self.assertNotIn("refreshConversations:", workspace_source)
        self.assertNotIn("apiClient.fetchConversations()", workspace_source)
        self.assertIn("async function refreshConversations()", conversation_workspace_source)
        self.assertIn("const conversationResponse = await apiClient.fetchConversations()", conversation_workspace_source)
        self.assertIn("setConversations(conversationResponse.sessions)", conversation_workspace_source)

    def test_conversation_model_control_moves_into_dedicated_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        page_model_source = self.source("frontend/src/features/conversations/useWorkspacePageModel.ts")
        model_control_source = self.source("frontend/src/features/conversations/useConversationModelControl.ts")

        for expected in [
            "async function chooseSessionModel",
            "function chooseThinkingMode",
            "function closeModelPickerOnOutsidePointerDown",
            "function resetModelControl",
        ]:
            self.assertIn(expected, model_control_source)
            self.assertNotIn(expected, workspace_source)
        self.assertIn("setVisionParseModel", model_control_source)
        self.assertIn("setVisionParseModel,", page_model_source)
        self.assertIn("setVisionParseModel(defaultsResponse?.defaults.vision_parse ?? null)", model_control_source)
        self.assertNotIn("apiClient.setDefaultModel(modelId)", model_control_source)

    def test_conversation_lifecycle_moves_into_dedicated_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        lifecycle_source = self.source("frontend/src/features/conversations/useConversationLifecycle.ts")

        self.assertIn("export function useConversationLifecycle", lifecycle_source)
        for expected in [
            "function navigateTo",
            "async function loadWorkspaceData",
            "setVisionParseModel(defaultsResponse?.defaults.vision_parse ?? null)",
            "function resetWorkspaceState",
            "async function openConversation",
            "async function openFavoriteSourceConversation",
            "async function openConversationFromSidebar",
            "async function signOut",
            "function switchView",
            "function startConversation",
            "async function deleteConversationFromSidebar",
        ]:
            self.assertIn(expected, lifecycle_source)
            self.assertNotIn(expected, workspace_source)
        self.assertIn("conversationRequestSeqRef.current += 1", lifecycle_source)
        self.assertIn("conversationSurfaceRef.current?.scrollTo", lifecycle_source)
        self.assertIn("apiClient.deleteConversation(sessionId)", lifecycle_source)

    def test_highlighted_message_scroll_moves_into_layout_hook(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        page_model_source = self.source("frontend/src/features/conversations/useWorkspacePageModel.ts")
        layout_source = self.source("frontend/src/features/conversations/useConversationLayout.ts")

        self.assertIn("messageRefs: MutableRefObject<Map<string, HTMLElement>>", layout_source)
        self.assertIn("messageRefs.current.get(highlightedMessageId)?.scrollIntoView", layout_source)
        self.assertIn("behavior: \"smooth\"", layout_source)
        self.assertIn("messageRefs,", page_model_source)
        self.assertNotIn("messageRefs.current.get(highlightedMessageId)?.scrollIntoView", workspace_source)

    def test_conversation_surface_rendering_moves_into_dedicated_component(self):
        workspace_source = self.source("frontend/src/features/conversations/WorkspacePage.tsx")
        conversation_surface_source = self.source(
            "frontend/src/features/conversations/ConversationWorkspaceSurface.tsx"
        )
        panel_source = self.source("frontend/src/features/conversations/ConversationWorkspacePanel.tsx")
        route_content_source = self.source("frontend/src/features/conversations/WorkspaceRouteContent.tsx")

        self.assertIn("export function ConversationWorkspaceSurface", conversation_surface_source)
        self.assertIn("ConversationWorkspacePanel", route_content_source)
        self.assertIn("ConversationWorkspaceSurface", panel_source)
        for expected in [
            "function renderMainWorkspace",
            "function renderConversationComposer",
            "function renderComposerModelControl",
            "function renderMessageBubble",
            "function renderBranchControls",
            "function shouldHideAssistantPlaceholderDuringThinking",
        ]:
            self.assertIn(expected, conversation_surface_source)
            self.assertNotIn(expected, workspace_source)
        self.assertIn("ConversationComposer", conversation_surface_source)
        self.assertIn("ConversationMessageBubble", conversation_surface_source)
        self.assertIn("HomeWorkspace", conversation_surface_source)

    def test_styles_are_split_by_frontend_surface(self):
        index_source = self.source("frontend/src/styles/index.css")
        shim_source = self.source("frontend/src/styles.css")
        base_source = self.source("frontend/src/styles/base.css")
        components_source = self.source("frontend/src/styles/components.css")
        shell_source = self.source("frontend/src/styles/shell.css")
        conversations_source = self.source("frontend/src/styles/conversations.css")
        composer_source = self.source("frontend/src/styles/composer.css")
        favorites_source = self.source("frontend/src/styles/favorites.css")
        settings_source = self.source("frontend/src/styles/settings.css")
        responsive_source = self.source("frontend/src/styles/responsive.css")

        for expected_import in [
            '@import "./tokens.css";',
            '@import "./base.css";',
            '@import "./components.css";',
            '@import "./shell.css";',
            '@import "./auth.css";',
            '@import "./conversations.css";',
            '@import "./composer.css";',
            '@import "./favorites.css";',
            '@import "./settings.css";',
            '@import "./responsive.css";',
        ]:
            self.assertIn(expected_import, index_source)

        self.assertLessEqual(len(shim_source.splitlines()), 20)
        self.assertIn('@import "./styles/index.css";', shim_source)

        self.assertLessEqual(len(base_source.splitlines()), 180)
        for feature_selector in [
            ".patient-",
            ".workspace-",
            ".conversation-",
            ".composer-",
            ".message-",
            ".favorite-",
            ".settings-",
            ".provider-",
            ".model-",
            ".resource-",
            "@media (max-width",
        ]:
            self.assertNotIn(feature_selector, base_source)
            self.assertNotIn(feature_selector, components_source)

        self.assertIn(".patient-shell", shell_source)
        self.assertIn(".markdown-content", components_source)
        self.assertIn(".secret-input", components_source)
        self.assertIn(".status-message", components_source)
        self.assertIn(".account-button", shell_source)
        self.assertNotIn(".account-menu", shell_source)
        self.assertIn(".workspace-panel", conversations_source)
        self.assertIn(".message-list", conversations_source)
        self.assertIn(".assistant-composer", composer_source)
        self.assertIn(".composer-model-popover", composer_source)
        self.assertIn(".favorite-layout", favorites_source)
        self.assertIn(".favorites-workspace .favorite-card", favorites_source)
        self.assertIn(".settings-shell", settings_source)
        self.assertIn(".provider-workspace", settings_source)
        self.assertIn("@media (max-width: 650px)", responsive_source)
        self.assertIn(".patient-main:has(.favorites-workspace)", responsive_source)


if __name__ == "__main__":
    unittest.main()
