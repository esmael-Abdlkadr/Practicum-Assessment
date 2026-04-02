import pytest

from app.services.auth_service import validate_password_strength


@pytest.mark.parametrize(
    "password,expected",
    [
        ("Short1!", False),
        ("alllowercasepassword", False),
        ("ALLUPPERCASE1234", False),
        ("NoDigitsOrSpecial", False),
        ("Valid@Pass1234", True),
        ("Another#Good9", True),
    ],
)
def test_validate_password_strength_cases(password, expected):
    ok, _ = validate_password_strength(password)
    assert ok is expected
