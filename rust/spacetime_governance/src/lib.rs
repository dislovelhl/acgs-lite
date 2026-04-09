//! ACGS-2 SpacetimeDB Governance Module
//!
//! Constitutional enforcement via SpacetimeDB reducers.
//! MACI separation of powers is enforced at the database level:
//! - Proposers submit actions
//! - Validators approve/deny (cannot validate own proposals)
//! - Executors carry out approved actions
//!
//! Constitutional Hash: 608508a9bd224290

use spacetimedb::{table, reducer, Identity, ReducerContext, Table, Timestamp};

// --- Tables ---

#[table(name = constitutional_principle, public)]
pub struct ConstitutionalPrinciple {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    pub hash: String,
    pub category: String,
    pub text: String,
    pub weight: f64,
    pub active: bool,
    pub created_at: Timestamp,
    pub amended_by: Option<u64>,
}

#[table(name = governance_decision, public)]
pub struct GovernanceDecision {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    pub tenant_id: String,
    pub action_hash: String,
    pub verdict: String,
    pub reasoning: String,
    pub principle_ids: Vec<u64>,
    pub proposer: Identity,
    pub validator: Option<Identity>,
    pub created_at: Timestamp,
}

#[table(name = maci_role_binding, public)]
pub struct MACIRoleBinding {
    #[primary_key]
    pub agent_identity: Identity,
    pub role: String,
    pub tenant_id: String,
    pub granted_at: Timestamp,
}

// --- Reducers ---

#[reducer]
pub fn register_agent(
    ctx: &ReducerContext,
    agent_identity: Identity,
    role: String,
    tenant_id: String,
) -> Result<(), String> {
    let valid_roles = ["proposer", "validator", "executor"];
    if !valid_roles.contains(&role.as_str()) {
        return Err(format!(
            "Invalid role '{}'. Must be one of: {:?}",
            role, valid_roles
        ));
    }

    // Check if already registered
    if ctx
        .db
        .maci_role_binding()
        .agent_identity()
        .find(agent_identity)
        .is_some()
    {
        return Err("Agent already has a role binding".into());
    }

    ctx.db.maci_role_binding().insert(MACIRoleBinding {
        agent_identity,
        role,
        tenant_id,
        granted_at: ctx.timestamp,
    });

    Ok(())
}

#[reducer]
pub fn propose_action(
    ctx: &ReducerContext,
    tenant_id: String,
    action_hash: String,
    reasoning: String,
    principle_ids: Vec<u64>,
) -> Result<(), String> {
    let binding = ctx
        .db
        .maci_role_binding()
        .agent_identity()
        .find(ctx.sender)
        .ok_or("No MACI role binding for caller")?;

    if binding.role != "proposer" {
        return Err("Only proposers can submit actions".into());
    }

    if binding.tenant_id != tenant_id {
        return Err("Tenant mismatch: agent not authorized for this tenant".into());
    }

    // Validate that referenced principles exist and are active
    for pid in &principle_ids {
        match ctx.db.constitutional_principle().id().find(*pid) {
            Some(p) if !p.active => {
                return Err(format!("Principle {} is not active", pid));
            }
            None => {
                return Err(format!("Principle {} does not exist", pid));
            }
            _ => {}
        }
    }

    ctx.db.governance_decision().insert(GovernanceDecision {
        id: 0,
        tenant_id,
        action_hash,
        verdict: "pending".into(),
        reasoning,
        principle_ids,
        proposer: ctx.sender,
        validator: None,
        created_at: ctx.timestamp,
    });

    Ok(())
}

#[reducer]
pub fn validate_decision(
    ctx: &ReducerContext,
    decision_id: u64,
    verdict: String,
    reasoning: String,
) -> Result<(), String> {
    let binding = ctx
        .db
        .maci_role_binding()
        .agent_identity()
        .find(ctx.sender)
        .ok_or("No MACI role binding for caller")?;

    if binding.role != "validator" {
        return Err("Only validators can approve/deny decisions".into());
    }

    let valid_verdicts = ["approved", "denied", "escalated"];
    if !valid_verdicts.contains(&verdict.as_str()) {
        return Err(format!(
            "Invalid verdict '{}'. Must be one of: {:?}",
            verdict, valid_verdicts
        ));
    }

    let mut decision = ctx
        .db
        .governance_decision()
        .id()
        .find(decision_id)
        .ok_or("Decision not found")?;

    if decision.verdict != "pending" {
        return Err(format!(
            "Decision already has verdict: {}",
            decision.verdict
        ));
    }

    // MACI core invariant: validator cannot be the proposer
    if decision.proposer == ctx.sender {
        return Err("MACI violation: agents cannot validate their own proposals".into());
    }

    if binding.tenant_id != decision.tenant_id {
        return Err("Tenant mismatch: validator not authorized for this tenant".into());
    }

    decision.verdict = verdict;
    decision.reasoning = reasoning;
    decision.validator = Some(ctx.sender);
    ctx.db.governance_decision().id().update(decision);

    Ok(())
}

#[reducer]
pub fn amend_principle(
    ctx: &ReducerContext,
    original_id: u64,
    new_category: String,
    new_text: String,
    new_weight: f64,
    amendment_hash: String,
) -> Result<(), String> {
    let binding = ctx
        .db
        .maci_role_binding()
        .agent_identity()
        .find(ctx.sender)
        .ok_or("No MACI role binding for caller")?;

    // Only validators can amend principles (constitutional authority)
    if binding.role != "validator" {
        return Err("Only validators can amend constitutional principles".into());
    }

    // Deactivate the original principle
    let mut original = ctx
        .db
        .constitutional_principle()
        .id()
        .find(original_id)
        .ok_or("Original principle not found")?;

    if !original.active {
        return Err("Cannot amend an already-inactive principle".into());
    }

    original.active = false;
    ctx.db.constitutional_principle().id().update(original);

    // Create the amended version
    ctx.db
        .constitutional_principle()
        .insert(ConstitutionalPrinciple {
            id: 0,
            hash: amendment_hash,
            category: new_category,
            text: new_text,
            weight: new_weight,
            active: true,
            created_at: ctx.timestamp,
            amended_by: Some(original_id),
        });

    Ok(())
}
