from github import Auth, GithubIntegration
from config import GITHUB_APP_ID, GITHUB_PRIVATE_KEY_PATH

def _read_private_key() -> str:
    with open(GITHUB_PRIVATE_KEY_PATH, "r", encoding="utf-8") as f:
        return f.read()

def get_installation_access_token(installation_id: int) -> str:
    private_key = _read_private_key()
    auth = Auth.AppAuth(int(GITHUB_APP_ID), private_key)
    integration = GithubIntegration(auth=auth)
    token_obj = integration.get_access_token(installation_id)
    return token_obj.token