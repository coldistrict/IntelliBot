"""add_generalized_semantic_scoring

Revision ID: c7e8f9a0b1c2
Revises: b6d7e8f9a0b1
Create Date: 2026-04-06 20:45:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c7e8f9a0b1c2"
down_revision: str | None = "b6d7e8f9a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


claim_family_enum = sa.Enum(
    "official_event",
    "macro_policy",
    "legal_case",
    "narrative_manual",
    "generic_manual",
    name="claim_family_enum",
)
evidence_role_enum = sa.Enum(
    "outcome",
    "direct_support",
    "direct_contradiction",
    "procedural",
    "background",
    "commentary",
    "timing",
    "sentiment",
    name="evidence_role_enum",
)
qualitative_label_enum = sa.Enum(
    "leans_yes",
    "leans_no",
    "mixed",
    "insufficient_basis",
    name="qualitative_label_enum",
)

postgres_claim_family_enum = postgresql.ENUM(
    "official_event",
    "macro_policy",
    "legal_case",
    "narrative_manual",
    "generic_manual",
    name="claim_family_enum",
    create_type=False,
)
postgres_evidence_role_enum = postgresql.ENUM(
    "outcome",
    "direct_support",
    "direct_contradiction",
    "procedural",
    "background",
    "commentary",
    "timing",
    "sentiment",
    name="evidence_role_enum",
    create_type=False,
)
postgres_qualitative_label_enum = postgresql.ENUM(
    "leans_yes",
    "leans_no",
    "mixed",
    "insufficient_basis",
    name="qualitative_label_enum",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    claim_family_column_enum: sa.Enum = claim_family_enum
    evidence_role_column_enum: sa.Enum = evidence_role_enum
    qualitative_label_column_enum: sa.Enum = qualitative_label_enum

    if dialect == "postgresql":
        op.execute("ALTER TYPE template_key_enum ADD VALUE IF NOT EXISTS 'legal_case'")
        op.execute("ALTER TYPE template_key_enum ADD VALUE IF NOT EXISTS 'narrative_manual'")
        op.execute("ALTER TYPE source_tier_enum ADD VALUE IF NOT EXISTS 'expert_analysis'")
        claim_family_enum.create(bind, checkfirst=True)
        evidence_role_enum.create(bind, checkfirst=True)
        qualitative_label_enum.create(bind, checkfirst=True)
        claim_family_column_enum = postgres_claim_family_enum
        evidence_role_column_enum = postgres_evidence_role_enum
        qualitative_label_column_enum = postgres_qualitative_label_enum

    op.add_column(
        "rule_parses",
        sa.Column("claim_family", claim_family_column_enum, nullable=True),
    )
    op.add_column("rule_parses", sa.Column("yes_condition", sa.Text(), nullable=True))
    op.add_column("rule_parses", sa.Column("no_condition", sa.Text(), nullable=True))
    op.add_column(
        "rule_parses",
        sa.Column(
            "directional_scoring_policy",
            sa.JSON(),
            nullable=True,
        ),
    )

    op.add_column(
        "analysis_runs",
        sa.Column(
            "numeric_estimate_available",
            sa.Boolean(),
            nullable=True,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("numeric_estimate_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("qualitative_label", qualitative_label_column_enum, nullable=True),
    )
    op.alter_column("analysis_runs", "p_hat", existing_type=sa.Float(), nullable=True)
    op.alter_column("analysis_runs", "p_low", existing_type=sa.Float(), nullable=True)
    op.alter_column("analysis_runs", "p_high", existing_type=sa.Float(), nullable=True)

    op.add_column(
        "fact_claims",
        sa.Column(
            "evidence_role",
            evidence_role_column_enum,
            nullable=True,
            server_default="background",
        ),
    )
    op.add_column(
        "factors",
        sa.Column(
            "evidence_role",
            evidence_role_column_enum,
            nullable=True,
            server_default="background",
        ),
    )
    op.add_column(
        "factors",
        sa.Column(
            "used_in_scoring",
            sa.Boolean(),
            nullable=True,
            server_default=sa.false(),
        ),
    )
    op.add_column("factors", sa.Column("exclusion_reason", sa.Text(), nullable=True))

    if dialect == "postgresql":
        op.execute(
            """
            UPDATE rule_parses
            SET claim_family = CASE template_detected::text
                WHEN 'official_event' THEN 'official_event'::claim_family_enum
                WHEN 'macro_policy' THEN 'macro_policy'::claim_family_enum
                WHEN 'legal_case' THEN 'legal_case'::claim_family_enum
                WHEN 'narrative_manual' THEN 'narrative_manual'::claim_family_enum
                ELSE 'generic_manual'::claim_family_enum
            END
            """
        )
        op.execute(
            """
            UPDATE rule_parses
            SET yes_condition = 'YES if ' || COALESCE(question_text, 'the claim') || ' is true.',
                no_condition = 'NO if the opposite of this claim is true: ' || COALESCE(question_text, 'the claim')
            """
        )
        op.execute(
            """
            UPDATE rule_parses
            SET directional_scoring_policy = CASE COALESCE(claim_family::text, template_detected::text)
                WHEN 'official_event' THEN
                    '{"allowed_roles":["outcome","direct_support","direct_contradiction"],"commentary_mode":"none","procedural_mode":"uncertainty_only"}'::json
                WHEN 'macro_policy' THEN
                    '{"allowed_roles":["outcome","direct_support","direct_contradiction","commentary"],"commentary_mode":"expert_only","procedural_mode":"uncertainty_only"}'::json
                WHEN 'legal_case' THEN
                    '{"allowed_roles":["outcome","direct_support","direct_contradiction","commentary"],"commentary_mode":"expert_only","procedural_mode":"uncertainty_only"}'::json
                WHEN 'narrative_manual' THEN
                    '{"allowed_roles":["outcome","direct_support","direct_contradiction","commentary"],"commentary_mode":"bounded","procedural_mode":"uncertainty_only"}'::json
                ELSE
                    '{"allowed_roles":["outcome","direct_support","direct_contradiction"],"commentary_mode":"none","procedural_mode":"uncertainty_only"}'::json
            END
            """
        )
        op.execute(
            """
            UPDATE analysis_runs
            SET numeric_estimate_available = TRUE
            WHERE numeric_estimate_available IS NULL
            """
        )
        op.execute(
            """
            UPDATE fact_claims
            SET evidence_role = CASE claim_type::text
                WHEN 'rule_note' THEN 'background'::evidence_role_enum
                WHEN 'opinion' THEN 'commentary'::evidence_role_enum
                WHEN 'forecast' THEN 'commentary'::evidence_role_enum
                WHEN 'social_signal' THEN 'sentiment'::evidence_role_enum
                ELSE 'background'::evidence_role_enum
            END
            WHERE evidence_role IS NULL
            """
        )
        op.execute(
            """
            UPDATE factors
            SET evidence_role = CASE stance::text
                WHEN 'yes' THEN 'direct_support'::evidence_role_enum
                WHEN 'no' THEN 'direct_contradiction'::evidence_role_enum
                ELSE 'background'::evidence_role_enum
            END
            WHERE evidence_role IS NULL
            """
        )
    else:
        op.execute(
            """
            UPDATE rule_parses
            SET claim_family = CASE template_detected
                WHEN 'official_event' THEN 'official_event'
                WHEN 'macro_policy' THEN 'macro_policy'
                WHEN 'legal_case' THEN 'legal_case'
                WHEN 'narrative_manual' THEN 'narrative_manual'
                ELSE 'generic_manual'
            END
            """
        )
        op.execute(
            """
            UPDATE rule_parses
            SET yes_condition = 'YES if ' || COALESCE(question_text, 'the claim') || ' is true.',
                no_condition = 'NO if the opposite of this claim is true: ' || COALESCE(question_text, 'the claim')
            """
        )
        op.execute(
            """
            UPDATE rule_parses
            SET directional_scoring_policy = CASE COALESCE(claim_family, template_detected)
                WHEN 'official_event' THEN
                    '{"allowed_roles":["outcome","direct_support","direct_contradiction"],"commentary_mode":"none","procedural_mode":"uncertainty_only"}'
                WHEN 'macro_policy' THEN
                    '{"allowed_roles":["outcome","direct_support","direct_contradiction","commentary"],"commentary_mode":"expert_only","procedural_mode":"uncertainty_only"}'
                WHEN 'legal_case' THEN
                    '{"allowed_roles":["outcome","direct_support","direct_contradiction","commentary"],"commentary_mode":"expert_only","procedural_mode":"uncertainty_only"}'
                WHEN 'narrative_manual' THEN
                    '{"allowed_roles":["outcome","direct_support","direct_contradiction","commentary"],"commentary_mode":"bounded","procedural_mode":"uncertainty_only"}'
                ELSE
                    '{"allowed_roles":["outcome","direct_support","direct_contradiction"],"commentary_mode":"none","procedural_mode":"uncertainty_only"}'
            END
            """
        )
        op.execute(
            """
            UPDATE analysis_runs
            SET numeric_estimate_available = 1
            WHERE numeric_estimate_available IS NULL
            """
        )
        op.execute(
            """
            UPDATE fact_claims
            SET evidence_role = CASE claim_type
                WHEN 'rule_note' THEN 'background'
                WHEN 'opinion' THEN 'commentary'
                WHEN 'forecast' THEN 'commentary'
                WHEN 'social_signal' THEN 'sentiment'
                ELSE 'background'
            END
            WHERE evidence_role IS NULL
            """
        )
        op.execute(
            """
            UPDATE factors
            SET evidence_role = CASE stance
                WHEN 'yes' THEN 'direct_support'
                WHEN 'no' THEN 'direct_contradiction'
                ELSE 'background'
            END
            WHERE evidence_role IS NULL
            """
        )

    op.execute(
        """
        UPDATE factors
        SET used_in_scoring = CASE
            WHEN stance != 'neutral' AND final_weight > 0 THEN TRUE
            ELSE FALSE
        END
        WHERE used_in_scoring IS NULL
        """
    )
    op.execute(
        """
        UPDATE factors
        SET exclusion_reason = CASE
            WHEN used_in_scoring THEN NULL
            ELSE 'Migrated from the pre-semantic scoring model; treated as contextual until rerun.'
        END
        WHERE exclusion_reason IS NULL
        """
    )

    op.alter_column("rule_parses", "claim_family", nullable=False)
    op.alter_column("rule_parses", "yes_condition", nullable=False)
    op.alter_column("rule_parses", "no_condition", nullable=False)
    op.alter_column("rule_parses", "directional_scoring_policy", nullable=False)
    op.alter_column("analysis_runs", "numeric_estimate_available", nullable=False)
    op.alter_column("fact_claims", "evidence_role", nullable=False)
    op.alter_column("factors", "evidence_role", nullable=False)
    op.alter_column("factors", "used_in_scoring", nullable=False)

    op.alter_column("analysis_runs", "numeric_estimate_available", server_default=None)
    op.alter_column("fact_claims", "evidence_role", server_default=None)
    op.alter_column("factors", "evidence_role", server_default=None)
    op.alter_column("factors", "used_in_scoring", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_column("factors", "exclusion_reason")
    op.drop_column("factors", "used_in_scoring")
    op.drop_column("factors", "evidence_role")
    op.drop_column("fact_claims", "evidence_role")

    op.alter_column("analysis_runs", "p_high", existing_type=sa.Float(), nullable=False)
    op.alter_column("analysis_runs", "p_low", existing_type=sa.Float(), nullable=False)
    op.alter_column("analysis_runs", "p_hat", existing_type=sa.Float(), nullable=False)
    op.drop_column("analysis_runs", "qualitative_label")
    op.drop_column("analysis_runs", "numeric_estimate_reason")
    op.drop_column("analysis_runs", "numeric_estimate_available")

    op.drop_column("rule_parses", "directional_scoring_policy")
    op.drop_column("rule_parses", "no_condition")
    op.drop_column("rule_parses", "yes_condition")
    op.drop_column("rule_parses", "claim_family")

    if dialect == "postgresql":
        qualitative_label_enum.drop(bind, checkfirst=True)
        evidence_role_enum.drop(bind, checkfirst=True)
        claim_family_enum.drop(bind, checkfirst=True)
        # Added values on template_key_enum and source_tier_enum are intentionally retained.
    else:
        qualitative_label_enum.drop(bind, checkfirst=True)
        evidence_role_enum.drop(bind, checkfirst=True)
        claim_family_enum.drop(bind, checkfirst=True)
