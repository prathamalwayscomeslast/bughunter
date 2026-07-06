from github import Github
from config import GITHUB_TEST_TOKEN

def comment_on_issue(repo_full_name: str, issue_number: int, message: str):
    gh = Github(GITHUB_TEST_TOKEN)
    repo = gh.get_repo(repo_full_name)
    issue = repo.get_issue(number=issue_number)
    issue.create_comment(message)