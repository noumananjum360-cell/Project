import datetime as dt

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nomload.licensing import license as lic


@pytest.fixture()
def keys():
    priv = Ed25519PrivateKey.generate()
    return priv, priv.public_key()


def mgr(home, pub):
    return lic.LicenseManager(home, None, pub)


def test_key_roundtrip_and_tiers(keys):
    priv, pub = keys
    for tier, bays in ((1, 1), (2, 4), (3, 255)):
        info = lic.decode_key(lic.make_key(priv, tier, 1000 + tier), pub)
        assert info.tier == tier and info.max_bays == bays and info.key_id == 1000 + tier


def test_forged_or_mistyped_key_rejected(keys):
    priv, pub = keys
    k = lic.make_key(priv, 2, 77)
    bad = k[:-3] + ("AAA" if not k.endswith("AAA") else "BBB")
    with pytest.raises(ValueError):
        lic.decode_key(bad, pub)
    other = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError):
        lic.decode_key(lic.make_key(other, 3, 1), pub)


def test_activation_locks_to_first_pc(home, keys, monkeypatch):
    priv, pub = keys
    m = mgr(home, pub)
    st = m.activate(lic.make_key(priv, 2, 5))
    assert st.licensed and st.max_bays == 4 and not st.watermark
    monkeypatch.setenv("NOMLOAD_FINGERPRINT", "another-pc")
    st2 = mgr(home, pub).status()
    assert not st2.licensed and "different computer" in st2.message


def test_machine_locked_activation_key(home, keys, monkeypatch):
    priv, pub = keys
    fp = lic.parse_request_code(lic.request_code())
    k = lic.make_key(priv, 1, 9, fp8=fp[:8])
    assert mgr(home, pub).activate(k).licensed
    monkeypatch.setenv("NOMLOAD_FINGERPRINT", "pc-b")
    with pytest.raises(ValueError, match="different computer"):
        mgr(home, pub).activate(k)


def test_revocation_list(home, keys, tmp_path):
    priv, pub = keys
    m = mgr(home, pub)
    k = lic.make_key(priv, 2, 4242)
    assert m.activate(k).licensed
    f = tmp_path / "revoked.nlr"
    f.write_bytes(lic.make_revocation(priv, [4242]))
    assert m.import_revocation(f) == 1
    assert not m.status().licensed
    with pytest.raises(ValueError, match="revoked"):
        m.activate(k)
    forged = tmp_path / "forged.nlr"
    forged.write_bytes(lic.make_revocation(Ed25519PrivateKey.generate(), [1]))
    with pytest.raises(Exception):
        m.import_revocation(forged)


def test_expired_key(home, keys):
    priv, pub = keys
    k = lic.make_key(priv, 2, 3, expiry=dt.date.today() - dt.timedelta(days=1))
    with pytest.raises(ValueError, match="expired"):
        mgr(home, pub).activate(k)


def test_trial_mode_and_expiry(home, keys):
    _priv, pub = keys
    m = mgr(home, pub)
    st = m.status()
    assert st.trial and st.usable and st.watermark and st.max_bays == lic.TRIAL_BAYS and st.days_left == 14
    import base64
    import time
    (home / ".fr").write_text(base64.b64encode(str(time.time() - 15 * 86400).encode()).decode())
    st = m.status()
    assert st.trial and st.expired and not st.usable


def test_clock_rollback_detected(home, keys):
    _priv, pub = keys
    import time
    (home / ".ls").write_text(str(time.time() + 10 * 86400))
    st = mgr(home, pub).status()
    assert st.expired and "clock" in st.message.lower()


def test_request_code_roundtrip():
    code = lic.request_code()
    assert len(lic.parse_request_code(code)) == 10
