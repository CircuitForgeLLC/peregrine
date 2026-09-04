# tests/test_integration_google_drive.py
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.integrations.google_drive import GoogleDriveIntegration


def _integration(**config_overrides):
    integ = GoogleDriveIntegration()
    config = {
        "folder_id": "folder123",
        "credentials_json": "~/credentials/google-drive-sa.json",
    }
    config.update(config_overrides)
    integ.connect(config)
    return integ


def test_connect_requires_folder_id_and_credentials():
    integ = GoogleDriveIntegration()
    assert integ.connect({"folder_id": "abc", "credentials_json": "x.json"}) is True
    assert integ.connect({"folder_id": "abc"}) is False
    assert integ.connect({}) is False


def test_test_returns_true_on_successful_api_call():
    integ = _integration()
    mock_service = MagicMock()
    mock_service.files().get().execute.return_value = {"id": "folder123", "name": "Peregrine"}

    with patch.object(integ, "_build_service", return_value=mock_service):
        assert integ.test() is True


def test_test_returns_false_on_api_error():
    integ = _integration()
    mock_service = MagicMock()
    mock_service.files().get().execute.side_effect = Exception("404 not found")

    with patch.object(integ, "_build_service", return_value=mock_service):
        assert integ.test() is False


def test_test_returns_false_when_credentials_file_missing():
    integ = _integration(credentials_json="/nonexistent/path/creds.json")

    with patch.object(integ, "_build_service", side_effect=FileNotFoundError("no such file")):
        assert integ.test() is False


def test_test_calls_files_get_with_configured_folder_id():
    integ = _integration(folder_id="my-folder-id")
    mock_service = MagicMock()

    with patch.object(integ, "_build_service", return_value=mock_service):
        integ.test()

    mock_service.files().get.assert_called_with(fileId="my-folder-id", fields="id,name,mimeType")


def test_build_service_uses_service_account_credentials():
    integ = _integration()
    with patch("google.oauth2.service_account.Credentials.from_service_account_file") as mock_creds, \
         patch("googleapiclient.discovery.build") as mock_build:
        mock_creds.return_value = MagicMock()
        integ._build_service()

    mock_creds.assert_called_once()
    scopes = mock_creds.call_args.kwargs.get("scopes")
    assert scopes == ["https://www.googleapis.com/auth/drive"]
    mock_build.assert_called_once_with("drive", "v3", credentials=mock_creds.return_value)
