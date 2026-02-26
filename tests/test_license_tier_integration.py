import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt


@pytest.fixture()
def license_env(tmp_path):
    """Returns (private_pem, public_path, license_path) for tier integration tests."""
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
    public_path = tmp_path / "public.pem"
    public_path.write_bytes(public_pem)
    license_path = tmp_path / "license.json"
    return private_pem, public_path, license_path


def _write_jwt_license(license_path, private_pem, tier="paid", days=30):
    now = datetime.now(timezone.utc)
    token = pyjwt.encode({
        "sub": "CFG-PRNG-TEST", "product": "peregrine", "tier": tier,
        "iat": now, "exp": now + timedelta(days=days),
    }, private_pem, algorithm="RS256")
    license_path.write_text(json.dumps({"jwt": token, "grace_until": None}))


def test_effective_tier_free_without_license(tmp_path):
    from app.wizard.tiers import effective_tier
    tier = effective_tier(
        profile=None,
        license_path=tmp_path / "missing.json",
        public_key_path=tmp_path / "key.pem",
    )
    assert tier == "free"


def test_effective_tier_paid_with_valid_license(license_env):
    private_pem, public_path, license_path = license_env
    _write_jwt_license(license_path, private_pem, tier="paid")
    from app.wizard.tiers import effective_tier
    tier = effective_tier(profile=None, license_path=license_path,
                          public_key_path=public_path)
    assert tier == "paid"


def test_effective_tier_dev_override_takes_precedence(license_env):
    """dev_tier_override wins even when a valid license is present."""
    private_pem, public_path, license_path = license_env
    _write_jwt_license(license_path, private_pem, tier="paid")

    class FakeProfile:
        dev_tier_override = "premium"

    from app.wizard.tiers import effective_tier
    tier = effective_tier(profile=FakeProfile(), license_path=license_path,
                          public_key_path=public_path)
    assert tier == "premium"
