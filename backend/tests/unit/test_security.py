"""
Security / Core Unit Tests
"""
import pytest
import time
import uuid as _uuid
from jose import JWTError

from app.core.security import (
    hash_password, verify_password,
    create_access_token, verify_access_token,
)


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        hashed = hash_password("SecurePass@123")
        assert hashed != "SecurePass@123"
        assert len(hashed) > 30

    def test_verify_correct_password(self):
        hashed = hash_password("MyPassword@1")
        assert verify_password("MyPassword@1", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("CorrectHorse")
        assert verify_password("WrongPass", hashed) is False

    def test_different_salts(self):
        """Same password should produce different hashes each time."""
        h1 = hash_password("SamePassword")
        h2 = hash_password("SamePassword")
        assert h1 != h2  # bcrypt uses random salt

    def test_empty_password_still_hashes(self):
        hashed = hash_password("")
        assert isinstance(hashed, str)
        assert verify_password("", hashed) is True


class TestJWT:
    def test_create_and_decode_token(self):
        user_id = str(_uuid.uuid4())
        # create_access_token(subject: str, role: str)
        token = create_access_token(subject=user_id, role="OFFICER")
        payload = verify_access_token(token)
        assert payload["sub"] == user_id
        assert payload["role"] == "OFFICER"

    def test_tampered_token_rejected(self):
        token = create_access_token(subject="user-123", role="VIEWER")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(JWTError):
            verify_access_token(tampered)

    def test_token_has_exp_claim(self):
        token = create_access_token(subject="user-456", role="ADMIN")
        payload = verify_access_token(token)
        assert "exp" in payload
        assert payload["exp"] > time.time()
