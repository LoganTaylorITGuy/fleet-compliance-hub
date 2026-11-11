"""Compliance thresholds: the one place to tune the demo rules.

These are simplified for illustration and are not regulatory advice. A real
build would confirm each interval against current FMCSA rules and the
carrier's own policies.
"""

# Anything due within this many days is yellow ("due soon").
WARNING_DAYS = 30

# An HOS violation within this many days makes the driver red.
HOS_VIOLATION_LOOKBACK_DAYS = 7

# Days between annual vehicle inspections.
ANNUAL_INSPECTION_INTERVAL_DAYS = 365

# Drug and alcohol test results that count as failed (red) or pending (yellow).
FAILED_TEST_RESULTS = frozenset({"positive", "refused"})
PENDING_TEST_RESULTS = frozenset({"pending"})

# Drivers with these statuses are left out of dashboards and counts.
INACTIVE_DRIVER_STATUSES = frozenset({"terminated"})
