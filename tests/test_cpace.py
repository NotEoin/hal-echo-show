"""CPace against the test vectors of draft-irtf-cfrg-cpace-21, appendix A and B.3."""

from __future__ import annotations

import pytest

from halecho import cpace, sodium

pytestmark = pytest.mark.skipif(sodium.available() is not None, reason="needs libsodium")

PRS = b"Password"
CI = bytes.fromhex("0b415f696e69746961746f720b425f726573706f6e646572")
SID = bytes.fromhex("7e4b4791d6a8ef019b936c79fb7f2c57")
G = bytes.fromhex("222b6b195fe84b1652badb6f6a3ae3d24341e7306967f0b8115b40d5698c7e56")
YA_SCALAR = bytes.fromhex("da3d23700a9e5699258aef94dc060dfda5ebb61f02a5ea77fad53f4ff0976d08")
YB_SCALAR = bytes.fromhex("d2316b454718c35362d83d69df6320f38578ed5984651435e2949762d900b80d")
YA = bytes.fromhex("d6bac480f2c386c394efc7c47adb9925dcd2630b64f240c50f8d0eec482b9157")
YB = bytes.fromhex("3ea7e0b19560d7c0b0f5734f63b955286dfa8232b5ebe63324e2d9e7433f7258")
ISK_IR = bytes.fromhex(
    "b69effbf61b51d56401c0f65601abe428de8206feaaf0e32198896dcae7b35cd"
    "2b38950a39dfd5d4a79164614c2984f7daa460b588c1e80c3fa2068af7900447"
)


def test_prepend_len_matches_the_draft():
    assert cpace.prepend_len(b"") == bytes.fromhex("00")
    assert cpace.prepend_len(b"1234") == bytes.fromhex("0431323334")
    assert cpace.prepend_len(bytes(range(128)))[:2] == bytes.fromhex("8001")


def test_lv_cat_matches_the_draft():
    assert cpace.lv_cat(b"1234", b"5", b"", b"678") == bytes.fromhex("043132333401350003363738")


def test_generator_string_is_170_bytes_with_100_bytes_of_padding():
    gen = cpace.generator_string(PRS, CI, SID)
    assert len(gen) == 170
    assert gen[28:128] == bytes(100)


def test_generator_matches_the_draft():
    assert cpace.calculate_generator(PRS, CI, SID) == G


def test_messages_and_isk_match_the_draft():
    a = cpace.CPace(PRS, CI, SID, b"ADa", scalar=YA_SCALAR)
    b = cpace.CPace(PRS, CI, SID, b"ADb", scalar=YB_SCALAR)
    assert a.message == YA
    assert b.message == YB
    assert a.finish(YB, b"ADb", initiator=True).isk == ISK_IR
    assert b.finish(YA, b"ADa", initiator=False).isk == ISK_IR


def test_same_code_confirms_both_ways():
    a = cpace.CPace(b"123456", CI, SID, b"device")
    b = cpace.CPace(b"123456", CI, SID, b"pc")
    ca = a.finish(b.message, b"pc", initiator=True)
    cb = b.finish(a.message, b"device", initiator=False)
    ca.check(cb.own_tag)
    cb.check(ca.own_tag)


def test_wrong_code_fails_confirmation():
    a = cpace.CPace(b"123456", CI, SID, b"device")
    b = cpace.CPace(b"123457", CI, SID, b"pc")
    cb = b.finish(a.message, b"device", initiator=False)
    with pytest.raises(cpace.PairingFailed):
        cb.check(a.finish(b.message, b"pc", initiator=True).own_tag)


def test_tampered_associated_data_fails_confirmation():
    a = cpace.CPace(b"123456", CI, SID, b"device-cert")
    b = cpace.CPace(b"123456", CI, SID, b"pc")
    cb = b.finish(a.message, b"attacker-cert", initiator=False)
    with pytest.raises(cpace.PairingFailed):
        cb.check(a.finish(b.message, b"pc", initiator=True).own_tag)


def test_invalid_peer_message_is_refused():
    a = cpace.CPace(b"123456", CI, SID, b"device")
    with pytest.raises(cpace.PairingFailed):
        a.finish(b"\xff" * 32, b"pc", initiator=True)
    with pytest.raises(cpace.PairingFailed):
        a.finish(bytes(32), b"pc", initiator=True)  # the identity element
