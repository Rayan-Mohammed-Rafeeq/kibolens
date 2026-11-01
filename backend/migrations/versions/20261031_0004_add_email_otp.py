"""add email and otp authentication

Revision ID: 20261031_0004
Revises: 20261031_0003
Create Date: 2026-10-31 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20261031_0004'
down_revision: Union[str, None] = '20261031_0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add email columns to users table
    op.add_column('users', sa.Column('email', sa.String(length=256), nullable=True))
    op.add_column('users', sa.Column('email_normalized', sa.String(length=256), nullable=True))
    
    # Create indexes on email columns
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_email_normalized'), 'users', ['email_normalized'], unique=True)
    
    # Create otp_challenges table
    op.create_table('otp_challenges',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('otp_digest', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('invalidated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_otp_challenges_user_id'), 'otp_challenges', ['user_id'], unique=False)


def downgrade() -> None:
    # Drop otp_challenges table
    op.drop_index(op.f('ix_otp_challenges_user_id'), table_name='otp_challenges')
    op.drop_table('otp_challenges')
    
    # Drop email columns from users
    op.drop_index(op.f('ix_users_email_normalized'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_column('users', 'email_normalized')
    op.drop_column('users', 'email')
