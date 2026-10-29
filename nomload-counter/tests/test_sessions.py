"""Session matching, tolerance, review, release, attribution and gate pass import."""
import pytest

from nomload.services.sessions import SessionError


@pytest.fixture()
def setup(app):
    bid = app.bays.save_bay(app.user, "Bay 1")
    flour = app.products.by_name("Flour 50kg bag")
    sugar = app.products.by_name("Sugar 50kg bag")
    carton = app.products.by_name("Carton 1.5L x6")
    return app, bid, flour, sugar, carton


def add(app, sid, cls, n, direction=1, flagged=False, active=None):
    for _ in range(n):
        app.sessions.add_event(sid, cls, direction, 0.3 if flagged else 0.9, flagged, active_product_id=active)


def test_exact_match_is_cleared(setup):
    app, bid, flour, _s, _c = setup
    gid = app.gate_passes.create(app.user, "GP-1", [(flour.id, 10)], "LES-4721")
    sid = app.sessions.start(bid, app.user, gid)
    add(app, sid, "bag", 11)
    add(app, sid, "bag", 1, direction=-1)
    s = app.sessions.close(sid, app.user)
    assert s.status == "cleared" and s.total_counted == 10
    assert app.gate_passes.get(gid).status == "completed"


def test_short_load_is_mismatch_and_needs_supervisor(setup):
    app, bid, flour, _s, _c = setup
    gid = app.gate_passes.create(app.user, "GP-2", [(flour.id, 10)])
    sid = app.sessions.start(bid, app.user, gid)
    add(app, sid, "bag", 8)
    s = app.sessions.close(sid, app.user)
    assert s.status == "mismatch" and s.lines[0].diff == -2
    clerk_id = app.auth.create_user("clerk1", "secret1", "clerk", actor=app.user)
    from nomload.services.context import User
    clerk = User(clerk_id, "clerk1", "", "clerk")
    with pytest.raises(SessionError):
        app.sessions.release(sid, clerk, "please let it go")
    sup = app.auth.verify_supervisor("admin", "1234")
    with pytest.raises(SessionError):
        app.sessions.release(sid, sup, "")          # reason required
    s = app.sessions.release(sid, sup, "2 bags short, customer informed")
    assert s.status == "released" and s.released_by


def test_tolerance_units_and_percent(setup):
    app, bid, flour, _s, _c = setup
    app.settings.set("tolerance_pct", 1.0)  # 1% of 400 = 4 units
    gid = app.gate_passes.create(app.user, "GP-3", [(flour.id, 400)])
    sid = app.sessions.start(bid, app.user, gid)
    add(app, sid, "bag", 397)
    assert app.sessions.close(sid, app.user).status == "cleared"
    app.products.save(app.user, flour.name, "bag", 1, tolerance_units=0, tolerance_pct=0.0, pid=flour.id)
    gid = app.gate_passes.create(app.user, "GP-4", [(flour.id, 400)])
    sid = app.sessions.start(bid, app.user, gid)
    add(app, sid, "bag", 399)
    assert app.sessions.close(sid, app.user).status == "mismatch"


def test_flagged_counts_need_review_before_clear(setup):
    app, bid, flour, _s, _c = setup
    gid = app.gate_passes.create(app.user, "GP-5", [(flour.id, 5)])
    sid = app.sessions.start(bid, app.user, gid)
    add(app, sid, "bag", 4)
    add(app, sid, "bag", 1, flagged=True)
    lines = app.sessions.lines(sid)
    assert lines[0].counted == 4 and lines[0].pending == 1
    sup = app.auth.verify_supervisor("admin", "1234")
    for e in app.sessions.pending_events(sid):
        app.sessions.review_event(e["id"], True, sup)
    assert app.sessions.close(sid, app.user).status == "cleared"


def test_units_per_detection_stack_rule(setup):
    app, bid, _f, _s, _c = setup
    pack = app.products.by_name("Shrink pack 500ml x12")
    app.products.save(app.user, pack.name, "pack", 12, pid=pack.id)
    gid = app.gate_passes.create(app.user, "GP-6", [(pack.id, 36)])
    sid = app.sessions.start(bid, app.user, gid)
    add(app, sid, "pack", 3)
    assert app.sessions.close(sid, app.user).status == "cleared"


def test_two_products_same_class_use_active_product(setup):
    app, bid, flour, sugar, carton = setup
    gid = app.gate_passes.create(app.user, "GP-7", [(flour.id, 3), (sugar.id, 2), (carton.id, 1)])
    sid = app.sessions.start(bid, app.user, gid)
    add(app, sid, "bag", 3, active=flour.id)
    add(app, sid, "bag", 2, active=sugar.id)
    add(app, sid, "carton", 1)              # unique class -> carton automatically
    s = app.sessions.close(sid, app.user)
    assert {l.name: l.counted for l in s.lines} == {flour.name: 3, sugar.name: 2, carton.name: 1}
    assert s.status == "cleared"


def test_product_not_on_gate_pass_is_mismatch(setup):
    app, bid, flour, _s, carton = setup
    gid = app.gate_passes.create(app.user, "GP-8", [(flour.id, 2)])
    sid = app.sessions.start(bid, app.user, gid)
    add(app, sid, "bag", 2)
    add(app, sid, "carton", 1)
    s = app.sessions.close(sid, app.user)
    assert s.status == "mismatch"


def test_session_without_gate_pass_then_link(setup):
    app, bid, flour, _s, _c = setup
    sid = app.sessions.start(bid, None, None, auto=True)
    add(app, sid, "bag", 4)
    gid = app.gate_passes.create(app.user, "GP-9", [(flour.id, 4)], "LEA-1234")
    assert app.gate_passes.match_plate("LEA 1234").id == gid
    assert app.gate_passes.match_plate("LFA-1234").id == gid  # one OCR error tolerated
    app.sessions.link_gate_pass(sid, gid, app.user)
    assert app.sessions.close(sid, app.user).status == "cleared"


def test_one_active_session_per_bay(setup):
    app, bid, flour, _s, _c = setup
    app.sessions.start(bid, app.user)
    with pytest.raises(SessionError):
        app.sessions.start(bid, app.user)


def test_manual_adjust_requires_supervisor_and_is_audited(setup):
    app, bid, flour, _s, _c = setup
    gid = app.gate_passes.create(app.user, "GP-10", [(flour.id, 5)])
    sid = app.sessions.start(bid, app.user, gid)
    add(app, sid, "bag", 4)
    sup = app.auth.verify_supervisor("admin", "1234")
    app.sessions.manual_adjust(sid, flour.id, 1, sup, "one bag hidden behind pillar, checked on video")
    assert app.sessions.close(sid, app.user).status == "cleared"
    assert app.db.scalar("SELECT COUNT(*) FROM audit_log WHERE action='count_adjusted'") == 1


def test_import_csv_groups_multi_product_gate_passes(app, tmp_path):
    p = tmp_path / "gp.csv"
    p.write_text("Gate Pass,Vehicle,Customer,Product,Quantity\nGP-100,LES-1,A,Flour 50kg bag,300\n"
                 "GP-100,LES-1,A,Sugar 50kg bag,50\nGP-101,TLA-2,B,Carton 1.5L x6,20\nGP-102,X,C,Unknown thing,5\n")
    n, errs = app.gate_passes.import_file(app.user, p)
    assert n == 2 and len(errs) == 1 and "Unknown thing" in errs[0]
    gp = app.gate_passes.by_number("GP-100")
    assert gp.total_expected == 350 and len(gp.items) == 2


def test_import_excel(app, tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["gate_pass", "vehicle", "product", "qty"])
    ws.append(["GP-200", "RIK-55", "Cement 50kg bag", 600])
    p = tmp_path / "gp.xlsx"
    wb.save(p)
    n, errs = app.gate_passes.import_file(app.user, p)
    assert n == 1 and not errs
