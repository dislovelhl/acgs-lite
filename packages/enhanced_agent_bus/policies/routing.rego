package acgs.routing

import future.keywords.if
import future.keywords.in

# Message Routing Policy - High-performance routing decisions
# Constitutional Hash: 608508a9bd224290
# P99 eval <1ms: O(1) object lookups, indexed equality checks

# OPTIMIZATION: Priority levels as object for O(1) lookup instead of array iteration
high_priority_levels := {"high": true, "critical": true}

# Default agent mapping by message type - already O(1) object lookup
default_agent_for_type := {
    "command": "command_processor",
    "query": "query_handler",
    "event": "event_dispatcher",
    "notification": "notification_service"
}

# OPTIMIZATION: Governance requests go to deliberation layer (check first - early exit)
# More specific rules evaluated first for faster short-circuiting
destination := {
    "agent": "deliberation_layer",
    "priority": "high",
    "queue": "governance"
} if {
    input.message.message_type == "governance_request"
    input.message.constitutional_hash == "608508a9bd224290"
}

# High priority messages go to high-priority queue
# Uses O(1) set lookup instead of array iteration
destination := {
    "agent": "high_priority_handler",
    "priority": "high",
    "queue": "priority"
} if {
    high_priority_levels[input.message.priority]
    input.message.constitutional_hash == "608508a9bd224290"
}

# Default routing based on message type (O(1) object lookup)
destination := {
    "agent": default_agent_for_type[input.message.message_type],
    "priority": input.message.priority
} if {
    input.message.constitutional_hash == "608508a9bd224290"
}
