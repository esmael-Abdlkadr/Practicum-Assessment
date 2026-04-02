from app.services.auth_service import generate_captcha, verify_captcha


def test_generate_captcha_has_question_and_answer():
    q, a = generate_captcha()
    assert "+" in q
    assert q.endswith("?")
    assert a.isdigit()


def test_verify_captcha_exact_match():
    assert verify_captcha("7", "7") is True


def test_verify_captcha_trimmed_match():
    assert verify_captcha(" 7 ", "7") is True


def test_verify_captcha_mismatch():
    assert verify_captcha("8", "7") is False
