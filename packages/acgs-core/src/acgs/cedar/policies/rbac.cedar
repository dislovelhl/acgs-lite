// ACGS RBAC Policy — Cedar equivalent of policies/rbac.rego
// Constitutional Hash: 608508a9bd224290
// NIST 800-53 AC-6, OWASP A01:2021 Broken Access Control

// Allow if user has the required role in the correct tenant
permit(
    principal,
    action,
    resource
) when {
    principal.tenant_id == resource.tenant_id &&
    principal.roles.contains(resource.required_role) &&
    resource.constitutional_hash == "608508a9bd224290"
};

// Block privilege escalation: only admins can perform admin actions
forbid(
    principal,
    action == Action::"admin_action",
    resource
) unless {
    principal.roles.contains("admin")
};

// Block delete: only admins and owners can delete
forbid(
    principal,
    action == Action::"delete",
    resource
) unless {
    principal.roles.contains("admin") ||
    principal.roles.contains("owner")
};
