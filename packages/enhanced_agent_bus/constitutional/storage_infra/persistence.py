"""
PostgreSQL Persistence for ACGS-2 Constitutional Storage.

Constitutional Hash: 608508a9bd224290
"""


from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..amendment_model import AmendmentProposal
from ..version_model import ConstitutionalStatus, ConstitutionalVersion
from .config import StorageConfig
from .models import AmendmentProposalDB, Base, ConstitutionalVersionDB

logger = get_logger(__name__)


class PersistenceManager:
    """Manages PostgreSQL persistence for constitutional versions and amendments."""

    def __init__(self, config: StorageConfig):
        self.config = config
        self.engine: object | None = None

    async def connect(self) -> bool:
        """Connect to PostgreSQL and create tables."""
        try:
            self.engine = create_async_engine(
                self.config.database_url,
                echo=False,
                future=True,
                pool_pre_ping=True,
                pool_recycle=3600,
            )

            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            return True
        except (ValueError, TypeError, OSError, RuntimeError) as e:
            logger.error(f"Failed to connect to database: {e}")
            self.engine = None
            return False

    async def disconnect(self) -> None:
        """Disconnect from PostgreSQL."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None

    async def save_version(self, version: ConstitutionalVersion, tenant_id: str) -> bool:
        """Save a constitutional version to PostgreSQL."""
        if not self.engine:
            return False

        try:
            async with AsyncSession(self.engine) as session:
                db_version = ConstitutionalVersionDB(
                    version_id=version.version_id,
                    tenant_id=tenant_id,
                    version=version.version,
                    constitutional_hash=version.constitutional_hash,
                    content=version.content,
                    predecessor_version=version.predecessor_version,
                    status=version.status.value,
                    extra_metadata=version.metadata,
                    created_at=version.created_at,
                    activated_at=version.activated_at,
                    deactivated_at=version.deactivated_at,
                )
                session.add(db_version)
                await session.commit()
                return True
        except (ValueError, TypeError, OSError, RuntimeError) as e:
            logger.error(f"Failed to save version {version.version_id}: {e}")
            return False

    async def get_version(self, version_id: str, tenant_id: str) -> ConstitutionalVersion | None:
        """Get a constitutional version from PostgreSQL."""
        if not self.engine:
            return None

        try:
            async with AsyncSession(self.engine) as session:
                stmt = select(ConstitutionalVersionDB).where(
                    ConstitutionalVersionDB.version_id == version_id,
                    ConstitutionalVersionDB.tenant_id == tenant_id,
                )
                result = await session.execute(stmt)
                db_version = result.scalar_one_or_none()
                return self._db_to_pydantic_version(db_version) if db_version else None
        except (ValueError, TypeError, OSError, RuntimeError) as e:
            logger.error(f"Failed to get version {version_id}: {e}")
            return None

    async def update_version(self, version: ConstitutionalVersion, tenant_id: str) -> bool:
        """Update a constitutional version in PostgreSQL."""
        if not self.engine:
            return False

        try:
            async with AsyncSession(self.engine) as session:
                stmt = select(ConstitutionalVersionDB).where(
                    ConstitutionalVersionDB.version_id == version.version_id,
                    ConstitutionalVersionDB.tenant_id == tenant_id,
                )
                result = await session.execute(stmt)
                db_version = result.scalar_one_or_none()

                if not db_version:
                    return False

                db_version.status = version.status.value  # type: ignore[assignment]
                db_version.extra_metadata = version.metadata  # type: ignore[assignment]
                db_version.activated_at = version.activated_at  # type: ignore[assignment]
                db_version.deactivated_at = version.deactivated_at  # type: ignore[assignment]

                await session.commit()
                return True
        except (ValueError, TypeError, OSError, RuntimeError) as e:
            logger.error(f"Failed to update version {version.version_id}: {e}")
            return False

    async def save_amendment(self, amendment: AmendmentProposal, tenant_id: str) -> bool:
        """Save an amendment proposal to PostgreSQL."""
        if not self.engine:
            return False

        try:
            async with AsyncSession(self.engine) as session:
                db_amendment = AmendmentProposalDB(
                    proposal_id=amendment.proposal_id,
                    tenant_id=tenant_id,
                    proposed_changes=amendment.proposed_changes,
                    justification=amendment.justification,
                    proposer_agent_id=amendment.proposer_agent_id,
                    target_version=amendment.target_version,
                    new_version=amendment.new_version,
                    status=amendment.status.value,
                    impact_score=str(amendment.impact_score) if amendment.impact_score else None,
                    impact_factors=amendment.impact_factors,
                    impact_recommendation=amendment.impact_recommendation,
                    requires_deliberation=str(amendment.requires_deliberation).lower(),
                    governance_metrics_before=amendment.governance_metrics_before,
                    governance_metrics_after=amendment.governance_metrics_after,
                    approval_chain=amendment.approval_chain,
                    rejection_reason=amendment.rejection_reason,
                    rollback_reason=amendment.rollback_reason,
                    extra_metadata=amendment.metadata,
                    created_at=amendment.created_at,
                    reviewed_at=amendment.reviewed_at,
                    activated_at=amendment.activated_at,
                    rolled_back_at=amendment.rolled_back_at,
                )
                session.add(db_amendment)
                await session.commit()
                return True
        except (ValueError, TypeError, OSError, RuntimeError) as e:
            logger.error(f"Failed to save amendment {amendment.proposal_id}: {e}")
            return False

    async def get_amendment(self, proposal_id: str, tenant_id: str) -> AmendmentProposal | None:
        """Get an amendment proposal from PostgreSQL."""
        if not self.engine:
            return None

        try:
            async with AsyncSession(self.engine) as session:
                stmt = select(AmendmentProposalDB).where(
                    AmendmentProposalDB.proposal_id == proposal_id,
                    AmendmentProposalDB.tenant_id == tenant_id,
                )
                result = await session.execute(stmt)
                db_amendment = result.scalar_one_or_none()
                return self._db_to_pydantic_amendment(db_amendment) if db_amendment else None
        except (ValueError, TypeError, OSError, RuntimeError) as e:
            logger.error(f"Failed to get amendment {proposal_id}: {e}")
            return None

    async def list_versions(
        self, tenant_id: str, limit: int = 50, offset: int = 0, status: str | None = None
    ) -> list[ConstitutionalVersion]:
        """list constitutional versions from PostgreSQL."""
        if not self.engine:
            return []

        try:
            async with AsyncSession(self.engine) as session:
                stmt = (
                    select(ConstitutionalVersionDB)
                    .where(ConstitutionalVersionDB.tenant_id == tenant_id)
                    .order_by(ConstitutionalVersionDB.created_at.desc())
                )
                if status:
                    stmt = stmt.where(ConstitutionalVersionDB.status == status)
                stmt = stmt.limit(limit).offset(offset)
                result = await session.execute(stmt)
                return [self._db_to_pydantic_version(db_v) for db_v in result.scalars().all()]
        except (ValueError, TypeError, OSError, RuntimeError) as e:
            logger.error(f"Failed to list versions: {e}")
            return []

    async def list_amendments(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        proposer_id: str | None = None,
    ) -> tuple[list[AmendmentProposal], int]:
        """list amendment proposals from PostgreSQL."""
        if not self.engine:
            return [], 0

        try:
            async with AsyncSession(self.engine) as session:
                stmt = select(AmendmentProposalDB).where(AmendmentProposalDB.tenant_id == tenant_id)
                count_stmt = select(func.count(AmendmentProposalDB.proposal_id)).where(
                    AmendmentProposalDB.tenant_id == tenant_id
                )

                if status:
                    stmt = stmt.where(AmendmentProposalDB.status == status)
                    count_stmt = count_stmt.where(AmendmentProposalDB.status == status)
                if proposer_id:
                    stmt = stmt.where(AmendmentProposalDB.proposer_agent_id == proposer_id)
                    count_stmt = count_stmt.where(
                        AmendmentProposalDB.proposer_agent_id == proposer_id
                    )

                count_res = await session.execute(count_stmt)
                total = count_res.scalar() or 0

                stmt = (
                    stmt.order_by(AmendmentProposalDB.created_at.desc()).limit(limit).offset(offset)
                )
                result = await session.execute(stmt)
                return [
                    self._db_to_pydantic_amendment(db_a) for db_a in result.scalars().all()
                ], total
        except (ValueError, TypeError, OSError, RuntimeError) as e:
            logger.error(f"Failed to list amendments: {e}")
            return [], 0

    async def get_active_version(self, tenant_id: str) -> ConstitutionalVersion | None:
        """Get active constitutional version from PostgreSQL."""
        if not self.engine:
            return None

        try:
            async with AsyncSession(self.engine) as session:
                stmt = select(ConstitutionalVersionDB).where(
                    ConstitutionalVersionDB.status == "active",
                    ConstitutionalVersionDB.tenant_id == tenant_id,
                )
                result = await session.execute(stmt)
                db_version = result.scalar_one_or_none()
                return self._db_to_pydantic_version(db_version) if db_version else None
        except (ValueError, TypeError, OSError, RuntimeError) as e:
            logger.error(f"Failed to get active version: {e}")
            return None

    def _db_to_pydantic_version(self, db_v: ConstitutionalVersionDB) -> ConstitutionalVersion:
        """Helper to convert DB version model to Pydantic."""
        return ConstitutionalVersion(
            version_id=db_v.version_id,
            version=db_v.version,
            constitutional_hash=db_v.constitutional_hash,
            content=db_v.content,
            predecessor_version=db_v.predecessor_version,
            status=ConstitutionalStatus(db_v.status),
            metadata=db_v.extra_metadata or {},
            created_at=db_v.created_at,
            activated_at=db_v.activated_at,
            deactivated_at=db_v.deactivated_at,
        )

    def _db_to_pydantic_amendment(self, db_a: AmendmentProposalDB) -> AmendmentProposal:
        """Helper to convert DB model to Pydantic."""
        return AmendmentProposal(
            proposal_id=db_a.proposal_id,
            proposed_changes=db_a.proposed_changes,
            justification=db_a.justification,
            proposer_agent_id=db_a.proposer_agent_id,
            target_version=db_a.target_version,
            new_version=db_a.new_version,
            status=db_a.status,
            impact_score=float(db_a.impact_score) if db_a.impact_score else None,
            impact_factors=db_a.impact_factors,
            impact_recommendation=db_a.impact_recommendation,
            requires_deliberation=db_a.requires_deliberation == "true",
            governance_metrics_before=db_a.governance_metrics_before,
            governance_metrics_after=db_a.governance_metrics_after,
            approval_chain=db_a.approval_chain,
            rejection_reason=db_a.rejection_reason,
            rollback_reason=db_a.rollback_reason,
            metadata=db_a.extra_metadata,
            created_at=db_a.created_at,
            reviewed_at=db_a.reviewed_at,
            activated_at=db_a.activated_at,
            rolled_back_at=db_a.rolled_back_at,
        )
