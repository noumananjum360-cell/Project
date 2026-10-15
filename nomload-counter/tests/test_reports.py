import datetime as dt


def test_reports_and_excel(app, tmp_path):
    bid = app.bays.save_bay(app.user, "Bay 1")
    flour = app.products.by_name("Flour 50kg bag")
    gid = app.gate_passes.create(app.user, "GP-R", [(flour.id, 3)], "LES-1")
    sid = app.sessions.start(bid, app.user, gid)
    for _ in range(2):
        app.sessions.add_event(sid, "bag", 1, 0.9, False)
    app.sessions.close(sid, app.user)
    d = dt.date.today()
    for name, fn in (("c.pdf", lambda p: app.reports.loading_certificate(sid, p)),
                     ("d.pdf", lambda p: app.reports.daily_dispatch(d, p)),
                     ("m.pdf", lambda p: app.reports.mismatch_report(d, d, p)),
                     ("x.xlsx", lambda p: app.reports.export_excel(d, d, p))):
        fn(tmp_path / name)
        assert (tmp_path / name).stat().st_size > 1500
    t = app.stats.today()
    assert t["trucks"] == 1 and t["mismatches"] == 1 and t["units_total"] == 2
    assert app.stats.insights()
