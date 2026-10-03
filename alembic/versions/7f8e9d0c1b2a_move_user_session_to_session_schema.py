"""move_user_session_to_session_schema

Revision ID: 7f8e9d0c1b2a
Revises: 59c7a358bd44
Create Date: 2026-08-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f8e9d0c1b2a'
down_revision: Union[str, None] = '59c7a358bd44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure the session schema exists
    op.execute("CREATE SCHEMA IF NOT EXISTS session")

    # Move sessions table from auth schema to session schema if it exists in auth,
    # or create it in session schema if running from scratch.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_schema = 'auth' AND table_name = 'sessions'
            ) THEN
                ALTER TABLE auth.sessions SET SCHEMA session;
            ELSIF NOT EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_schema = 'session' AND table_name = 'sessions'
            ) THEN
                CREATE TABLE session.sessions (
                    id UUID NOT NULL,
                    user_id UUID NOT NULL,
                    refresh_token_hash VARCHAR(255) NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    ip_address VARCHAR(45) NULL,
                    user_agent TEXT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    last_active_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    CONSTRAINT pk_sessions PRIMARY KEY (id),
                    CONSTRAINT fk_sessions_user_id_users FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE
                );
                CREATE UNIQUE INDEX ix_session_sessions_refresh_token_hash ON session.sessions (refresh_token_hash);
                CREATE INDEX ix_session_sessions_user_active ON session.sessions (user_id, is_active);
                CREATE INDEX ix_session_sessions_user_id ON session.sessions (user_id);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_schema = 'session' AND table_name = 'sessions'
            ) THEN
                ALTER TABLE session.sessions SET SCHEMA auth;
            END IF;
        END $$;
    """)
