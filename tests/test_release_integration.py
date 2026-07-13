from src.sync import sync_topology_entry, SyncResult
from src.config import SyncSettings, TopologyEntry, Endpoint
from src.strategies.base import StrategyResult

def test_sync_topology_entry_runs_release_sync(monkeypatch):
    import src.release_sync as rs
    import src.sync as s
    captured = {}
    def _fake_sync_releases(entry, creds, settings):
        captured["called"] = True
        return rs.ReleaseSyncResult(releases_created=2)
    monkeypatch.setattr(rs, "sync_releases", _fake_sync_releases)

    # 避免真实 clone / head 读取
    monkeypatch.setattr(s, "clone_or_fetch", lambda *a, **k: None)
    monkeypatch.setattr(s, "get_head_sha", lambda *a, **k: "abc")
    # 让分支同步策略 no-op 成功
    import src.strategies.mirror as m
    monkeypatch.setattr(m.MirrorStrategy, "sync", lambda self, **kw: StrategyResult(success=True))

    entry = TopologyEntry(
        name="x",
        source=Endpoint(platform="github", owner="o", repo="r", branch="main", auth="ssh"),
        targets=[Endpoint(platform="gitee", owner="o", repo="r", branch="main", auth="ssh")],
    )
    res = sync_topology_entry(
        entry=entry, creds={}, work_dir="/tmp/wt",
        url_overrides={"github": "x", "gitee": "y"},
        bypass_credentials=True,
        settings=SyncSettings(sync_releases=True),
    )
    assert captured.get("called") is True
    assert res.release_result is not None and res.release_result.releases_created == 2

def test_sync_topology_entry_release_off_by_default(monkeypatch):
    import src.release_sync as rs
    called = {"v": False}
    monkeypatch.setattr(rs, "sync_releases", lambda entry, creds, settings: called.__setitem__("v", True) or rs.ReleaseSyncResult())
    import src.sync as s
    monkeypatch.setattr(s, "clone_or_fetch", lambda *a, **k: None)
    monkeypatch.setattr(s, "get_head_sha", lambda *a, **k: "abc")
    import src.strategies.mirror as m
    monkeypatch.setattr(m.MirrorStrategy, "sync", lambda self, **kw: StrategyResult(success=True))
    entry = TopologyEntry(
        name="x",
        source=Endpoint(platform="github", owner="o", repo="r", branch="main", auth="ssh"),
        targets=[Endpoint(platform="gitee", owner="o", repo="r", branch="main", auth="ssh")],
    )
    sync_topology_entry(entry=entry, creds={}, work_dir="/tmp/wt",
                        url_overrides={"github": "x", "gitee": "y"}, bypass_credentials=True,
                        settings=SyncSettings(sync_releases=False))
    assert called["v"] is False
