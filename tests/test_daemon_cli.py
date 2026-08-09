from pocket_agent import daemon


def test_session_lifecycle():
    s = daemon.start_session(goal="test", project="pytest")
    assert s["id"].startswith("sess-")
    hb = daemon.heartbeat(s["id"], note="tick")
    assert hb["ok"]
    g = daemon.set_goal(s["id"], "ship it")
    assert g["ok"]
    d = daemon.detach(s["id"])
    assert d["ok"]
    a = daemon.attach(s["id"])
    assert a and a["status"] == "detached"
    r = daemon.resume(s["id"])
    assert r and r["status"] == "running"
    daemon.stop_session(s["id"])


def test_doctor_and_schedule():
    d = daemon.doctor(fix=True)
    assert d["ok"] or d.get("fixes")
    sch = daemon.schedule_add(every_seconds=60, note="nudge")
    assert sch["ok"]
    assert any(x["id"] == sch["id"] for x in daemon.list_schedules())
    daemon.disable_schedule(sch["id"])


def test_service_status():
    daemon.ensure_service()
    st = daemon.service_status()
    assert st["ok"]
    assert "sessions" in st
