from typing import List, Dict, Any, Optional
import gitlab
from langchain.tools import BaseTool
from pydantic import Field
import logging

logger = logging.getLogger(__name__)


class GitLabTools:
    def __init__(self, token: str, url: str = "https://gitlab.com"):
        self.gl = gitlab.Gitlab(url, private_token=token)

    def get_mr_details(self, project_id: str, mr_iid: int) -> Dict[str, Any]:
        """Get comprehensive MR details including files and diffs."""
        try:
            project = self.gl.projects.get(project_id)
            mr = project.mergerequests.get(mr_iid)
            changes = mr.changes()

            files = []
            for change in changes.get("changes", []):
                diff = change.get("diff", "")
                additions = diff.count("\n+") if diff else 0
                deletions = diff.count("\n-") if diff else 0

                files.append({
                    "filename": change.get("new_path", change.get("old_path", "")),
                    "status": "renamed" if change.get("renamed_file") else
                              "deleted" if change.get("deleted_file") else
                              "added" if change.get("new_file") else "modified",
                    "additions": additions,
                    "deletions": deletions,
                    "patch": diff[:2000] if diff else "",
                })

            return {
                'title': mr.title,
                'body': mr.description or '',
                'state': mr.state,
                'author': mr.author.get("username", "unknown") if isinstance(mr.author, dict) else str(mr.author),
                'base_branch': mr.target_branch,
                'head_branch': mr.source_branch,
                'files': files,
                'changes_count': len(files),
                'sha': mr.sha,
            }

        except Exception as e:
            logger.error(f"Error getting MR details: {e}")
            raise

    def post_mr_note(self, project_id: str, mr_iid: int, comment: str) -> bool:
        """Post a note (comment) to a Merge Request."""
        try:
            project = self.gl.projects.get(project_id)
            mr = project.mergerequests.get(mr_iid)
            mr.notes.create({"body": comment})
            return True

        except Exception as e:
            logger.error(f"Error posting MR note: {e}")
            return False


class GetMRDetailsTool(BaseTool):
    name: str = "get_mr_details"
    description: str = "Get comprehensive Merge Request details including files and diffs."
    gitlab_tools: GitLabTools = Field(exclude=True)

    def _run(self, project_id: str, mr_iid: int) -> str:
        """Get MR details and return as formatted string."""
        details = self.gitlab_tools.get_mr_details(project_id, mr_iid)

        formatted_output = f"""
            MR Details:
            Title: {details['title']}
            Author: {details['author']}
            Base Branch: {details['base_branch']} ← Head Branch: {details['head_branch']}
            State: {details['state']}

            Description:
            {details['body']}

            Files Changed ({details['changes_count']}):

            Changed Files:
        """

        for file in details['files'][:10]:
            formatted_output += f"\n📁 {file['filename']} ({file['status']})\n"
            formatted_output += f"   +{file['additions']} -{file['deletions']} lines\n"
            if file['patch']:
                formatted_output += f"   Diff preview:\n{file['patch'][:500]}...\n"

        return formatted_output


class PostMRNoteTool(BaseTool):
    name: str = "post_mr_note"
    description: str = "Post a review note on a GitLab Merge Request"
    gitlab_tools: GitLabTools = Field(exclude=True)

    def _run(self, project_id: str, mr_iid: int, comment: str) -> str:
        """Post MR note and return success status."""
        success = self.gitlab_tools.post_mr_note(project_id, mr_iid, comment)
        return "MR note posted successfully!" if success else "Failed to post MR note."
