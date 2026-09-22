"""SAG configuration from the pinned benchmark; independent of MultiConfig."""
from typing import Literal
from pydantic import BaseModel as PipelineBaseModel, Field

class SAGRecallConfig(PipelineBaseModel):
    """SAG 召回配置"""

    max_entities: int = Field(
        default=15, ge=1, le=100, description="query→entity BM25/向量召回数量"
    )
    query_recall_event_max: int = Field(
        default=20, ge=1, le=200, description="路A query→event 保留上限"
    )
    max_events_per_key: int = Field(
        default=10, ge=1, le=100, description="每个实体读取的关系数上限"
    )
    entity_vector_threshold: float = Field(
        default=0.9, ge=0.0, le=1.0, description="LOCAL 实体向量匹配阈值"
    )
    score_threshold: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Path A/B 相似度过滤阈值"
    )


class SAGExpandConfig(PipelineBaseModel):
    """SAG 多跳扩展配置"""

    enabled: bool = Field(default=True, description="是否启用扩展")
    max_hops: int = Field(default=1, ge=0, le=2, description="扩展跳数")
    entities_per_hop: int = Field(default=15, ge=1, le=100, description="每跳新增实体上限")
    max_events_per_hop: int = Field(default=50, ge=1, le=500, description="每跳新增事项上限")
    event_similarity_threshold: float = Field(
        default=0.4, ge=0.0, le=1.0, description="expand 中 entity→event 相似度阈值"
    )
    entity_relation_score_threshold: float = Field(
        default=0.45,
        ge=0.0,
        le=1.0,
        description="expand 中 event→new key 关系向量阈值（ES kNN cosine 过滤）",
    )
    seed_event_limit: int = Field(default=15, ge=1, le=100, description="种子 event 取 top N")
    relation_k_multiplier: int = Field(
        default=3,
        ge=1,
        le=10,
        description="event→new key 关系打分候选放大倍率（relation_k = entities_per_hop × 此值）",
    )


class SAGScopeConfig(PipelineBaseModel):
    # Optional bounded SAG candidate-pool and in-memory subgraph scope.

    enabled: bool = Field(
        default=False,
        description="Build a bounded event/entity universe before SAG recall.",
    )
    event_top_k: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Number of top query-similar events used to bootstrap the scope.",
    )
    bootstrap_entity_limit: int = Field(
        default=0,
        ge=0,
        le=1000000,
        description="Optional cap on event-entity relations; 0 means unlimited.",
    )
    include_event_content: bool = Field(
        default=True,
        description="Keep event content in memory for ranking; chunks remain SQL hydrated.",
    )


class SAGRerankConfig(PipelineBaseModel):
    """SAG 排序配置"""

    strategy: Literal["rerank", "llm_rank", "rrf"] = Field(
        default="llm_rank", description="排序策略"
    )
    score_threshold: float = Field(
        default=0.3, ge=0.0, le=1.0, description="候选 event 向量相似度阈值"
    )
    rerank_score_threshold: float = Field(
        default=0.0, ge=0.0, le=1.0, description="rerank 模型分阈值"
    )
    rerank_top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="rerank 模型真正保留的结果数；不足 max_results 时按 embedding 相似度补齐",
    )
    rrf_k: int = Field(default=60, ge=1, description="RRF 名次融合常数")
    max_results: int = Field(default=10, ge=1, le=100, description="最终返回事项数")
    rerank_timeout: float = Field(default=60.0, ge=1.0, le=60.0, description="rerank 超时秒数")
    llm_rank_top_n: int = Field(default=100, ge=1, le=200, description="送 LLM 前粗排上限")
    llm_rank_max_results: int = Field(default=5, ge=1, le=20, description="LLM 排序返回上限")
    llm_rank_include_content: bool = Field(default=True, description="LLM 排序是否带全文")
    llm_rank_max_content_len: int = Field(
        default=2000, ge=100, description="每条 content 截断字符数"
    )
    llm_rank_prompt: str = Field(
        default="llm_rank_events",
        description="LLM 排序模板名（select_useful_relations_local=KG 关系选择 / llm_rank_events=index+score）",
    )


class SAGConfig(PipelineBaseModel):
    """Independent SAG configuration — decoupled from MultiConfig.

    SAG reads only this config. MultiES continues to read MultiConfig.
    The two config classes share no inheritance relationship.
    """

    strategy: Literal["sag"] = "sag"

    use_mlflow_prompts: bool = Field(
        default=False,
        description="是否从 MLflow Prompt Registry 加载提示词（启动时一次性加载并打印来源；"
        "未注册的条目回退到代码常量，服务不可达则报错）。默认 False=全用代码常量。",
    )
    mlflow_prompt_alias: str = Field(
        default="latest",
        description="MLflow Prompt Registry 别名（use_mlflow_prompts=True 时生效）。"
        "加载时使用 prompts:/name@{alias}，默认为 latest。"
        "可设为 production/staging 等具名别名实现版本切换。",
    )
    mlflow_tracking_uri: str | None = Field(
        default=None,
        description="MLflow Tracking URI（use_mlflow_prompts=True 时透传给 PromptProvider，"
        "用于确保 prompt 加载使用正确的 HTTP endpoint）。"
        "传入后 PromptProvider.load_all() 会调用 mlflow.set_tracking_uri(该值)。",
    )

    max_sections: int = Field(
        default=10, ge=1, le=50, description="最终返回段落最大数量（chunk_id 去重后截断）"
    )

    sag_recall: SAGRecallConfig = Field(
        default_factory=SAGRecallConfig, description="SAG 召回配置"
    )
    sag_scope: SAGScopeConfig = Field(default_factory=SAGScopeConfig)
    sag_expand: SAGExpandConfig = Field(
        default_factory=SAGExpandConfig, description="SAG 多跳扩展配置"
    )
    sag_rerank: SAGRerankConfig = Field(
        default_factory=SAGRerankConfig, description="SAG 排序配置"
    )

    sag_rewrite_query_enabled: bool = Field(default=False, description="SAG LLM 问题重写开关")
    sag_enable_entity_extraction: bool = Field(
        default=True,
        description="SAG 独立 NER 开关（默认开启，对齐 benchmark --foundation search）",
    )
    sag_use_fast_mode: bool = Field(default=False, description="SAG 快速模式（跳过 LLM 排序）")

