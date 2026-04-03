// ACGS MACI Role Separation — Cedar policy
// Constitutional Hash: 608508a9bd224290
// Enforces Trias Politica separation of powers

// Proposers can draft, propose, suggest, amend, read, query
permit(
    principal is Agent,
    action in [Action::"propose", Action::"draft", Action::"suggest", Action::"amend", Action::"read", Action::"query"],
    resource
) when {
    principal.maci_role == "proposer"
};

// Validators can validate, review, audit, verify, read, query
permit(
    principal is Agent,
    action in [Action::"validate", Action::"review", Action::"audit", Action::"verify", Action::"read", Action::"query"],
    resource
) when {
    principal.maci_role == "validator"
};

// Executors can execute, deploy, apply, run, read, query
permit(
    principal is Agent,
    action in [Action::"execute", Action::"deploy", Action::"apply", Action::"run", Action::"read", Action::"query"],
    resource
) when {
    principal.maci_role == "executor"
};

// Observers can only read, query, export, observe
permit(
    principal is Agent,
    action in [Action::"read", Action::"query", Action::"export", Action::"observe"],
    resource
) when {
    principal.maci_role == "observer"
};

// Proposers cannot validate, execute, or approve
forbid(
    principal is Agent,
    action in [Action::"validate", Action::"execute", Action::"approve"],
    resource
) when {
    principal.maci_role == "proposer"
};

// Validators cannot propose, execute, or deploy
forbid(
    principal is Agent,
    action in [Action::"propose", Action::"execute", Action::"deploy"],
    resource
) when {
    principal.maci_role == "validator"
};

// Executors cannot validate, propose, or approve
forbid(
    principal is Agent,
    action in [Action::"validate", Action::"propose", Action::"approve"],
    resource
) when {
    principal.maci_role == "executor"
};
