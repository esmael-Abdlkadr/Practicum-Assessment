from app.services import encryption_service


def test_encrypt_decrypt_roundtrip():
    plain = "20240001234"
    enc = encryption_service.encrypt(plain)
    dec = encryption_service.decrypt(enc)
    assert dec == plain


def test_mask_student_id_expected_output():
    assert encryption_service.mask_student_id("20240001234") == "*******1234"


def test_mask_student_id_short_values():
    assert encryption_service.mask_student_id("1234") == "****"
