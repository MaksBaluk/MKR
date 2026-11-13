"""Initial MVP schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-13
"""
from alembic import op
from backend.db import Base
import backend.models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    Base.metadata.create_all(bind=connection)
    if connection.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("""CREATE TABLE IF NOT EXISTS competency_vectors (
            competency_id varchar(90) PRIMARY KEY REFERENCES competencies(id) ON DELETE CASCADE,
            model varchar(100) NOT NULL,
            embedding vector(384) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )""")
        op.execute("""CREATE INDEX IF NOT EXISTS ix_competency_vectors_hnsw
            ON competency_vectors USING hnsw (embedding vector_cosine_ops)""")


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS competency_vectors")
    Base.metadata.drop_all(bind=connection)
