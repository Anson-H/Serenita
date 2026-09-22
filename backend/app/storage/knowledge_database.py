from backend.app.storage.schema import (
    CheckConstraint, Column, ColumnGroup as G, Database, ForeignKey, Index, Table,
)
from backend.app.storage.business_change_database import BUSINESS_CHANGE_TABLES


KNOWLEDGE_DATABASE_SCHEMA = Database(
    name="knowledge.db",
    tables=(
        Table(
            name="knowledge_documents",
            columns=(
                Column("document_id", "TEXT", G.PRIMARY_KEY, nullable=False),
                Column("original_filename", "TEXT", G.DATA, nullable=False),
                Column("mime_type", "TEXT", G.DATA, nullable=False),
                Column("size_bytes", "INTEGER", G.DATA, nullable=False),
                Column("sha256", "TEXT", G.DATA, nullable=False),
                Column("content_bytes", "BLOB", G.DATA, nullable=False),
                Column("segment_count", "INTEGER", G.STATE, nullable=False),
                Column("created_at", "DATETIME", G.AUDIT, nullable=False),
            ),
            primary_key=("document_id",),
            checks=(CheckConstraint("size_bytes > 0"), CheckConstraint("segment_count > 0")),
            indexes=(Index("knowledge_created", ("created_at", "document_id")),),
        ),
        Table(
            name="knowledge_segments",
            columns=(
                Column("document_id", "TEXT", G.PRIMARY_KEY, nullable=False),
                Column("segment_index", "INTEGER", G.PRIMARY_KEY, nullable=False),
                Column("page_number", "INTEGER", G.DATA),
                Column("content", "TEXT", G.DATA, nullable=False, non_blank=False),
                Column("token_count", "INTEGER", G.STATE, nullable=False),
            ),
            primary_key=("document_id", "segment_index"),
            foreign_keys=(ForeignKey(("document_id",), "knowledge_documents", ("document_id",), on_delete="CASCADE"),),
            checks=(CheckConstraint("segment_index > 0"), CheckConstraint("page_number IS NULL OR page_number > 0"), CheckConstraint("token_count >= 0")),
        ),
        Table(
            name="knowledge_terms",
            columns=(
                Column("document_id", "TEXT", G.PRIMARY_KEY, nullable=False),
                Column("segment_index", "INTEGER", G.PRIMARY_KEY, nullable=False),
                Column("term", "TEXT", G.PRIMARY_KEY, nullable=False),
                Column("frequency", "INTEGER", G.STATE, nullable=False),
            ),
            primary_key=("document_id", "segment_index", "term"),
            foreign_keys=(ForeignKey(("document_id", "segment_index"), "knowledge_segments", ("document_id", "segment_index"), on_delete="CASCADE"),),
            checks=(CheckConstraint("frequency > 0"),),
            indexes=(Index("knowledge_term_lookup", ("term",)),),
        ),
        *BUSINESS_CHANGE_TABLES,
    ),
)
