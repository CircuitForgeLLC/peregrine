# tests/test_credential_store.py
"""Regression coverage for credential_store.py's per-directory (multi-tenant)
isolation. Found live on peregrine-cloud 2026-09-23: get_credential()/
set_credential() always used the module-wide CRED_DIR (co-located with the
app install, not on the per-tenant data volume) -- every cloud tenant's IMAP
app password wrote to and read from the same encrypted file, silently
overwriting each other's credentials, and the file was wiped on every
container restart since it wasn't on persistent per-tenant storage.
"""
from scripts.credential_store import delete_credential, get_credential, set_credential


def test_set_and_get_credential_uses_given_cred_dir(tmp_path):
    """A credential written with an explicit cred_dir is readable from that
    same cred_dir, and does not touch the module-wide default location."""
    cred_dir = tmp_path / "tenant-a" / "credentials"
    set_credential("peregrine", "imap_password", "app-password-1", cred_dir=cred_dir)

    assert (cred_dir / "peregrine.json").exists()
    assert get_credential("peregrine", "imap_password", cred_dir=cred_dir) == "app-password-1"


def test_different_cred_dirs_do_not_collide(tmp_path):
    """Two 'tenants' (different cred_dir values) storing the same service/key
    combination must not see or overwrite each other's value -- this is
    the exact bug: CRED_DIR used to be a single shared path regardless of
    which tenant's request triggered the read/write."""
    tenant_a_dir = tmp_path / "tenant-a" / "credentials"
    tenant_b_dir = tmp_path / "tenant-b" / "credentials"

    set_credential("peregrine", "imap_password", "tenant-a-password", cred_dir=tenant_a_dir)
    set_credential("peregrine", "imap_password", "tenant-b-password", cred_dir=tenant_b_dir)

    assert get_credential("peregrine", "imap_password", cred_dir=tenant_a_dir) == "tenant-a-password"
    assert get_credential("peregrine", "imap_password", cred_dir=tenant_b_dir) == "tenant-b-password"


def test_get_credential_with_cred_dir_returns_none_when_unset(tmp_path):
    cred_dir = tmp_path / "tenant-a" / "credentials"
    assert get_credential("peregrine", "imap_password", cred_dir=cred_dir) is None


def test_delete_credential_scoped_to_cred_dir(tmp_path):
    tenant_a_dir = tmp_path / "tenant-a" / "credentials"
    tenant_b_dir = tmp_path / "tenant-b" / "credentials"
    set_credential("peregrine", "imap_password", "tenant-a-password", cred_dir=tenant_a_dir)
    set_credential("peregrine", "imap_password", "tenant-b-password", cred_dir=tenant_b_dir)

    delete_credential("peregrine", "imap_password", cred_dir=tenant_a_dir)

    assert get_credential("peregrine", "imap_password", cred_dir=tenant_a_dir) is None
    assert get_credential("peregrine", "imap_password", cred_dir=tenant_b_dir) == "tenant-b-password"


def test_credential_file_is_encrypted_not_plaintext(tmp_path):
    """The stored password must never appear as a readable substring of the
    on-disk file -- confirms Fernet encryption is actually happening, not
    silently falling back to the plaintext path."""
    cred_dir = tmp_path / "tenant-a" / "credentials"
    secret = "super-secret-app-password-xyz"
    set_credential("peregrine", "imap_password", secret, cred_dir=cred_dir)

    raw = (cred_dir / "peregrine.json").read_bytes()
    assert secret.encode() not in raw
