from typing import Any


class ReportImportWriteConflictError(RuntimeError):
    code = "REPORT_IMPORT_WRITE_CONFLICT"

    def __init__(self, message: str, *, details: list[dict[str, Any]]):
        super().__init__(message)
        self.detail = {"code": self.code, "message": message, "details": details}


class LabDictionaryRevisionConflictError(RuntimeError):
    code = "LAB_DICTIONARY_REVISION_CONFLICT"


class LabDictionaryNameConflictError(RuntimeError):
    code = "LAB_DICTIONARY_NAME_CONFLICT"

    def __init__(
        self,
        message: str,
        *,
        conflicting_item_id: str | None = None,
        conflicting_item_name_zh: str | None = None,
    ):
        super().__init__(message)
        self.detail = {
            "code": self.code,
            "message": message,
        }
        if conflicting_item_id:
            self.detail["conflicting_item_id"] = conflicting_item_id
        if conflicting_item_name_zh:
            self.detail["conflicting_item_name_zh"] = conflicting_item_name_zh


class LabDictionaryMergeResultConflictError(RuntimeError):
    code = "LAB_DICTIONARY_MERGE_RESULT_CONFLICT"

    def __init__(self, message: str, *, details: list[dict[str, Any]]):
        super().__init__(message)
        self.detail = {"code": self.code, "message": message, "details": details}


class LabDictionaryPrimaryCategoryError(RuntimeError):
    code = "LAB_DICTIONARY_PRIMARY_CATEGORY_IN_USE"
