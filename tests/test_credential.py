"""Tests for credential loading from environment."""
import pytest

from src.credential import (
    Credential,
    CredentialError,
    load_credentials,
    get_secret_name,
)


def test_get_secret_name_ssh():
    assert get_secret_name("github", "ssh") == "SSH_KEY_GITHUB"
    assert get_secret_name("gitee", "ssh") == "SSH_KEY_GITEE"
    assert get_secret_name("gitcode", "ssh") == "SSH_KEY_GITCODE"


def test_get_secret_name_pat():
    assert get_secret_name("github", "pat") == "TOKEN_GITHUB"
    assert get_secret_name("gitee", "pat") == "TOKEN_GITEE"
    assert get_secret_name("cnb", "pat") == "TOKEN_CNB"
    assert get_secret_name("gitcode", "pat") == "TOKEN_GITCODE"


def test_credential_dataclass():
    c = Credential(ssh_key="key1", pat="pat1")
    assert c.ssh_key == "key1"
    assert c.pat == "pat1"
    assert c.has_ssh is True
    assert c.has_pat is True

    c2 = Credential()
    assert c2.has_ssh is False
    assert c2.has_pat is False


def test_load_credentials_missing_all_raises(monkeypatch):
    # Clear all relevant env vars
    for k in [
        "SSH_KEY_GITHUB", "TOKEN_GITHUB",
        "SSH_KEY_GITEE", "TOKEN_GITEE",
        "TOKEN_CNB",
        "SSH_KEY_GITCODE", "TOKEN_GITCODE",
    ]:
        monkeypatch.delenv(k, raising=False)
    # All platforms have at least one credential configured by default in
    # our test fixture pattern; for this test we simulate "no creds for github"
    # by removing only the github env vars, and we expect the loader to still
    # succeed for other platforms. Use a stricter helper:
    with pytest.raises(CredentialError):
        load_credentials(required={"github"})


def test_load_credentials_collects_all_set(monkeypatch):
    monkeypatch.setenv("SSH_KEY_GITHUB", "k1")
    monkeypatch.setenv("TOKEN_GITEE", "t1")
    monkeypatch.setenv("TOKEN_CNB", "c1")
    monkeypatch.setenv("SSH_KEY_GITCODE", "k2")
    creds = load_credentials()
    assert creds["github"].ssh_key == "k1"
    assert creds["github"].pat is None
    assert creds["gitee"].pat == "t1"
    assert creds["gitee"].ssh_key is None
    assert creds["cnb"].pat == "c1"
    assert creds["gitcode"].ssh_key == "k2"


def test_load_credentials_required_missing_raises(monkeypatch):
    monkeypatch.delenv("SSH_KEY_GITHUB", raising=False)
    monkeypatch.delenv("TOKEN_GITHUB", raising=False)
    monkeypatch.setenv("TOKEN_GITEE", "t1")
    monkeypatch.setenv("TOKEN_CNB", "c1")
    monkeypatch.setenv("SSH_KEY_GITCODE", "k1")
    with pytest.raises(CredentialError, match="github"):
        load_credentials(required={"github"})


def test_load_credentials_returns_empty_for_unset(monkeypatch):
    # Clear all
    for k in [
        "SSH_KEY_GITHUB", "TOKEN_GITHUB",
        "SSH_KEY_GITEE", "TOKEN_GITEE",
        "TOKEN_CNB",
        "SSH_KEY_GITCODE", "TOKEN_GITCODE",
    ]:
        monkeypatch.delenv(k, raising=False)
    creds = load_credentials()
    assert creds["github"] == Credential()
    assert creds["gitee"] == Credential()
    assert creds["cnb"] == Credential()
    assert creds["gitcode"] == Credential()