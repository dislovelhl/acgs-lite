package acgs.timebased

import future.keywords.if

default allow := false

# Check business hours for non-admin roles
allow if {
    input.context.role == "admin"
    input.constitutional_hash == "608508a9bd224290"
}

allow if {
    is_business_hours
    input.constitutional_hash == "608508a9bd224290"
}

allow if {
    input.context.after_hours_permission == true
    input.constitutional_hash == "608508a9bd224290"
}

# Business hours check (9 AM - 6 PM, Mon-Fri)
is_business_hours if {
    hour := time.clock([time.now_ns()])[0]
    day := time.weekday([time.now_ns()])
    hour >= 9
    hour < 18
    day >= 1  # Monday
    day <= 5  # Friday
}
