"""Active business/governance defaults that are safe before commercial launch."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PolicyItem:
    key: str
    status: str
    active_default: str
    rationale: str
    change_gate: str


def active_product_policy() -> dict:
    items = (
        PolicyItem(
            key="pricing_metering",
            status="active_safe_default",
            active_default="cost_observability_only_no_billing",
            rationale=(
                "Meter calls, tokens, USD, run, and monthly reservations for cost control; "
                "do not invoice or alter access based on a commercial plan."
            ),
            change_gate="User selects per-seat, per-run, or enterprise contract and legal terms.",
        ),
        PolicyItem(
            key="source_strategy",
            status="active_safe_default",
            active_default="private_repository_no_redistribution",
            rationale=(
                "No open-source license has been approved; third-party license review remains open."
            ),
            change_gate="User approves license, public/private boundaries, and dependency review.",
        ),
        PolicyItem(
            key="election_eligibility",
            status="active_governance_control",
            active_default="verified_admin_only_aggregate_output",
            rationale=(
                "Election scenarios remain aggregate-only and require an explicitly verified admin."
            ),
            change_gate=(
                "Human legal and ethics review approves eligible organizations and workflow."
            ),
        ),
        PolicyItem(
            key="semantic_memory",
            status="disabled_pending_evidence",
            active_default="run_local_reflection_only",
            rationale=(
                "Long-term autonomous memory adds privacy, drift, and cost risk without "
                "measured benefit."
            ),
            change_gate=(
                "Pre-registered benchmark across at least 30 paired runs shows >=10% quality gain, "
                "<=20% cost/token overhead, no cross-workspace leakage, and human approval."
            ),
        ),
    )
    return {
        "version": "2026-07-16.p8-m8",
        "billing_enabled": False,
        "repository_public": False,
        "semantic_memory_enabled": False,
        "items": [asdict(item) for item in items],
        "note": "Active safety defaults, not a commercial offer or legal determination.",
    }
