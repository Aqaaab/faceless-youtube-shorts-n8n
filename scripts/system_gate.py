    assert rules["final_quality_gate_required"] is True
    daily = (ROOT / ".github/workflows/daily-production.yml").read_text(encoding="utf-8")
    recovery = (ROOT / ".github/workflows/production-recovery.yml").read_text(encoding="utf-8")
    assert "python scripts/production.py" in daily
    assert "python scripts/production.py" in recovery
    assert "python scripts/system_gate.py" in daily
    assert "CAR_MODE: '1'" in daily and "CAR_MODE: '1'" in recovery
    assert "PEXELS_API_KEY" in daily and "YOUTUBE_REFRESH_TOKEN" in daily
    assert "ODYSSEUS_GATEWAY_BASE_URL" in daily and "ODYSSEUS_GATEWAY_API_KEY" in daily
    assert "workflow_run:" in daily
    assert "workflows: [Car Encyclopedia CI]" in daily
    assert "types: [completed]" in daily
    assert "workflow_dispatch:" in daily
    assert "github.event_name == 'workflow_dispatch'" in daily
    assert "github.event.workflow_run.conclusion == 'success'" in daily
    assert "github.event.workflow_run.head_branch == 'main'" in daily
    assert "github.event.workflow_run.event == 'push'" in daily
    assert "startsWith(github.event.workflow_run.head_commit.message, '[run-production]')" not in daily
    assert "schedule:" not in daily
    assert "cron:" not in daily
    assert "push:" not in daily
    assert "workflow_run:" in recovery
    assert "workflows: [Daily Production]" in recovery
    assert "types: [completed]" in recovery
    assert "github.event.workflow_run.conclusion == 'failure'" in recovery
    assert "github.event.workflow_run.head_branch == 'main'" in recovery
    assert "workflows: [Car Encyclopedia CI]" not in recovery
    assert "push:" not in recovery
    assert "workflow_dispatch:" not in recovery
    production_py = (ROOT / "scripts/production.py").read_text(encoding="utf-8")
    required_gate_markers = (