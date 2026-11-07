"""Preliminary inventory must be honest and pinned; not a false security attestation."""
from scripts.verify_component_inventory import verify


def test_preliminary_inventory_matches_committed_locks():
    inventory = verify()
    assert inventory["classification"] == (
        "PRELIMINARY_COMPONENT_INVENTORY_NOT_A_COMPLETE_SBOM"
    )
    assert len(inventory["ci_python_3_11_packages"]) == 6
    assert len(inventory["foundation_weight_revisions"]) == 3


def test_scoped_security_scan_does_not_overstate_independent_review():
    inventory = verify()
    assert inventory["cve_scan_performed"] is True
    assert inventory["cve_scan_final_review_completed"] is False
    assert inventory["licenses_transitive_reviewed"] is False
    assert all(not x["approved_for_runtime"]
               for x in inventory["review_only_repositories"])
    assert all(not x["downloaded"] and not x["approved_for_trading"]
               for x in inventory["foundation_weight_revisions"])
