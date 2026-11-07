"""Security findings must retain provenance, severity and fail-closed status."""
import pytest

from scripts.verify_security_triage import TriageError, classify, verify


def test_dated_security_evidence_is_consistent_and_not_suppressed():
    data = verify()
    ci = data["scopes"]["ci_environment"]
    src = data["scopes"]["repository_sources"]
    assert ci["matched_advisories"] == 10
    assert ci["severities"]["High"] == 2
    assert src["matched_advisories"] == 146
    assert src["severities"]["Critical"] == 5
    assert src["severities"]["High"] == 56
    assert src["origins"] == {"uninstalled_archived_midas_uv_lock": 146}
    assert data["g0_approved"] is False
    assert data["archived_midas_runtime_approved"] is False
    assert data["live_trading_permitted"] is False


@pytest.mark.parametrize(("scope", "path"), [
    ("repository_sources", "/src/goldintel/requirements.lock"),
    ("ci_environment", "/lib/python3.11/site-packages/newpkg.dist-info/RECORD"),
    ("unknown", "/vendor/snapshots/andyluu98--midas-agent/uv.lock"),
])
def test_unclassified_findings_are_never_ignored(scope, path):
    with pytest.raises(TriageError):
        classify(scope, [path])


def test_installed_bootstrap_findings_are_not_mistaken_for_midas_vendor():
    assert classify("ci_environment", [
        "/lib/python3.11/site-packages/pip-24.0.dist-info/METADATA"
    ]) == "ci_bootstrap_pip"
    assert classify("repository_sources", [
        "/vendor/snapshots/andyluu98--midas-agent/uv.lock"
    ]) == "uninstalled_archived_midas_uv_lock"
