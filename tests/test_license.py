import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt
from datetime import datetime, timedelta, timezone


@pytest.fixture()
def test_keys(tmp_path):
    """Generate test RSA keypair and return (private_pem, public_pem, public_path)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_path = tmp_path / "test_public.pem"
    public_path.write_bytes(public_pem)
    return private_pem, public_pem, public_path


def _make_jwt(private_pem: bytes, tier: str = "paid",
              product: str = "peregrine",
              exp_delta_days: int = 30,
              machine: str = "test-machine") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "CFG-PRNG-TEST-TEST-TEST",
        "product": product,
        "tier": tier,
        "seats": 1,
        "machine": machine,
        "iat": now,
        "exp": now + timedelta(days=exp_delta_days),
    }
    return pyjwt.encode(payload, private_pem, algorithm="RS256")


def _write_license(tmp_path, jwt_token: str, grace_until: str | None = None) -> Path:
    data = {
        "jwt": jwt_token,
        "key_display": "CFG-PRNG-TEST-TEST-TEST",
        "tier": "paid",
        "valid_until": None,
        "machine_id": "test-machine",
        "last_refresh": datetime.now(timezone.utc).isoformat(),
        "grace_until": grace_until,
    }
    p = tmp_path / "license.json"
    p.write_text(json.dumps(data))
    return p


class TestVerifyLocal:
    def test_valid_jwt_returns_tier(self, test_keys, tmp_path):
        private_pem, _, public_path = test_keys
        token = _make_jwt(private_pem)
        license_path = _write_license(tmp_path, token)
        from scripts.license import verify_local
        result = verify_local(license_path=license_path, public_key_path=public_path)
        assert result is not None
        assert result["tier"] == "paid"

    def test_missing_file_returns_none(self, tmp_path):
        from scripts.license import verify_local
        result = verify_local(license_path=tmp_path / "missing.json",
                              public_key_path=tmp_path / "key.pem")
        assert result is None

    def test_wrong_product_returns_none(self, test_keys, tmp_path):
        private_pem, _, public_path = test_keys
        token = _make_jwt(private_pem, product="falcon")
        license_path = _write_license(tmp_path, token)
        from scripts.license import verify_local
        result = verify_local(license_path=license_path, public_key_path=public_path)
        assert result is None

    def test_expired_within_grace_returns_tier(self, test_keys, tmp_path):
        private_pem, _, public_path = test_keys
        token = _make_jwt(private_pem, exp_delta_days=-1)
        grace_until = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        license_path = _write_license(tmp_path, token, grace_until=grace_until)
        from scripts.license import verify_local
        result = verify_local(license_path=license_path, public_key_path=public_path)
        assert result is not None
        assert result["tier"] == "paid"
        assert result["in_grace"] is True

    def test_expired_past_grace_returns_none(self, test_keys, tmp_path):
        private_pem, _, public_path = test_keys
        token = _make_jwt(private_pem, exp_delta_days=-10)
        grace_until = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        license_path = _write_license(tmp_path, token, grace_until=grace_until)
        from scripts.license import verify_local
        result = verify_local(license_path=license_path, public_key_path=public_path)
        assert result is None


class TestEffectiveTier:
    def test_returns_free_when_no_license(self, tmp_path):
        from scripts.license import effective_tier
        result = effective_tier(
            license_path=tmp_path / "missing.json",
            public_key_path=tmp_path / "key.pem",
        )
        assert result == "free"

    def test_returns_tier_from_valid_jwt(self, test_keys, tmp_path):
        private_pem, _, public_path = test_keys
        token = _make_jwt(private_pem, tier="premium")
        license_path = _write_license(tmp_path, token)
        from scripts.license import effective_tier
        result = effective_tier(license_path=license_path, public_key_path=public_path)
        assert result == "premium"
