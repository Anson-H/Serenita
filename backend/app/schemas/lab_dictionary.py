from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _DictionaryWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_dictionary_revision: str = Field(min_length=1)


class _LabItemFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_name_zh: str = Field(min_length=1, max_length=128)
    aliases: list[str] = Field(default_factory=list, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    primary_category_name: str = Field(min_length=1, max_length=64)
    related_category_names: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("item_name_zh")
    @classmethod
    def normalize_item_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("指标名称不能为空白。")
        return normalized

    @field_validator("aliases", "related_category_names")
    @classmethod
    def normalize_string_lists(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("primary_category_name")
    @classmethod
    def normalize_primary_category(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("主分类不能为空白。")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: Optional[str]) -> Optional[str]:
        normalized = str(value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def keep_primary_out_of_related(self):
        self.related_category_names = [
            value
            for value in self.related_category_names
            if value != self.primary_category_name
        ]
        return self


class CreateLabItemRequest(_DictionaryWriteRequest, _LabItemFields):
    pass


class UpdateLabItemRequest(_DictionaryWriteRequest, _LabItemFields):
    pass


class MergeLabDictionaryItemsRequest(_DictionaryWriteRequest):
    target_item_id: str = Field(min_length=1, max_length=128)

    @field_validator("target_item_id")
    @classmethod
    def normalize_target_item_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("目标指标 ID 不能为空白。")
        return normalized


class DeleteLabDictionaryEntryRequest(_DictionaryWriteRequest):
    pass


class DeleteLabDictionaryCategoryRequest(_DictionaryWriteRequest):
    pass


class _LabCategoryFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_name: str = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("category_name")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("分类名称不能为空白。")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        normalized = str(value or "").strip()
        return normalized or None


class CreateLabCategoryRequest(_DictionaryWriteRequest, _LabCategoryFields):
    pass


class UpdateLabCategoryRequest(_DictionaryWriteRequest, _LabCategoryFields):
    pass
