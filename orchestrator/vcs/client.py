from github import Github
from vcs.auth import get_installation_access_token

def comment_on_issue(installation_id: int, repo_full_name: str, issue_number: int, message: str):
    access_token = get_installation_access_token(installation_id)
    gh = Github(access_token)
    repo = gh.get_repo(repo_full_name)
    issue = repo.get_issue(number=issue_number)
    issue.create_comment(message)