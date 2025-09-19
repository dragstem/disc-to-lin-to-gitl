"""GitLab API client for creating issues."""

import logging
import requests
from typing import Dict, List, Optional
from src.config_manager import ConfigManager

class GitLabClient:
    """Client for interacting with GitLab REST API."""

    def __init__(self, config: ConfigManager, project_id: Optional[str] = None) -> None:
        """Initialize GitLab client.

        Args:
            config: Configuration manager instance
            project_id: Optional GitLab project ID override
        """
        self.token = config.gitlab_token
        self.project_id = project_id or config.gitlab_project_id
        self.base_url = config.gitlab_base_url
        self.session = requests.Session()
        self.session.headers.update({
            "PRIVATE-TOKEN": self.token,
            "Content-Type": "application/json"
        })

    def set_project_id(self, project_id: str) -> None:
        """Update the project ID for this client.

        Args:
            project_id: New GitLab project ID
        """
        self.project_id = project_id

    def _make_request(self, method: str, endpoint: str, payload: Optional[Dict] = None) -> Dict:
        """Make HTTP request to GitLab API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            payload: Request payload (for POST/PUT)

        Returns:
            JSON response data

        Raises:
            Exception: If request fails
        """
        url = f"{self.base_url}/{endpoint}"
        logger = logging.getLogger(__name__)

        try:
            if method.upper() == 'POST':
                response = self.session.post(url, json=payload, timeout=15)
            elif method.upper() == 'GET':
                response = self.session.get(url, timeout=15)
            elif method.upper() == 'PUT':
                response = self.session.put(url, json=payload, timeout=15)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Log detailed information for non-200 responses
            if not response.ok:
                logger.error(f"GitLab API {method} request failed: {url}")
                logger.error(f"Status Code: {response.status_code}")
                logger.error(f"Response Headers: {dict(response.headers)}")

                # Try to get response text safely
                try:
                    response_text = response.text
                    if response_text:
                        logger.error(f"Response Body: {response_text}")
                    else:
                        logger.error("Response Body: (empty)")
                except Exception as e:
                    logger.error(f"Failed to read response body: {str(e)}")

                # Log additional context
                if payload and method.upper() in ['POST', 'PUT']:
                    logger.error(f"Request Payload: {payload}")
                logger.error(f"Request Headers: {dict(self.session.headers)}")

            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"GitLab API request failed: {str(e)}")
            raise Exception(f"GitLab API request failed: {str(e)}")

    def create_issue(self, identifier: str, title: str, description: Optional[str] = None,
                    labels: Optional[List[str]] = None, assignee_id: Optional[int] = None,
                    due_date: Optional[str] = None, weight: Optional[int] = None) -> str:
        """Create a new GitLab issue with comprehensive field support.

        Args:
            identifier: Linear issue identifier (e.g., 'ABO-1')
            title: Original issue title
            description: Issue description
            labels: List of label names to apply
            assignee_id: GitLab user ID for assignee
            due_date: Due date in ISO format (YYYY-MM-DD)
            weight: Issue weight (0-9 for priority mapping)

        Returns:
            Created GitLab issue ID

        Raises:
            Exception: If issue creation fails
        """
        formatted_title = f"[{identifier}] {title}"
        payload = {
            "title": formatted_title,
            "description": description or "",
            "labels": labels or [],
            # Always create as open
            "state": "open"
        }

        # Add optional fields
        if assignee_id is not None:
            payload["assignee_ids"] = [assignee_id]
        if due_date:
            payload["due_date"] = due_date
        if weight is not None:
            payload["weight"] = weight

        endpoint = f"projects/{self.project_id}/issues"
        data = self._make_request('POST', endpoint, payload)

        # Return the issue ID (Iid or id depending on response)
        gitlab_issue_id = data.get('iid') or str(data.get('id', ''))
        return gitlab_issue_id

    def get_issue(self, issue_iid: str) -> Optional[Dict]:
        """Get details of a GitLab issue.

        Args:
            issue_iid: GitLab issue IID

        Returns:
            Issue details dictionary or None if not found
        """
        try:
            endpoint = f"projects/{self.project_id}/issues/{issue_iid}"
            return self._make_request('GET', endpoint)
        except Exception:
            return None

    def update_issue(self, issue_iid: str, update_data: Dict) -> None:
        """Update an existing GitLab issue with comprehensive field support.

        Args:
            issue_iid: GitLab issue IID
            update_data: Dictionary of fields to update
                           Supports: title, description, labels, assignee_id,
                           due_date, weight, state
        """
        endpoint = f"projects/{self.project_id}/issues/{issue_iid}"

        # Handle assignee update separately if provided
        if 'assignee_id' in update_data:
            assignee_id = update_data.pop('assignee_id')
            update_data['assignee_ids'] = [assignee_id] if assignee_id else []

        try:
            self._make_request('PUT', endpoint, update_data)
        except Exception as e:
            raise Exception(f"Failed to update GitLab issue {issue_iid}: {str(e)}")

    def add_test_issue(self, title_prefix: str = "Test") -> str:
        """Create a test issue (for testing purposes).

        Args:
            title_prefix: Prefix for test title

        Returns:
            Created GitLab issue IID
        """
        test_title = f"{title_prefix} - Linear-GitLab Sync Test"
        test_description = "This is a test issue created by the synchronization application."
        return self.create_issue("TEST-001", test_title, test_description, ["test", "auto-sync"])

    def get_project_info(self) -> Dict:
        """Get information about the GitLab project.

        Returns:
            Project details dictionary
        """
        endpoint = f"projects/{self.project_id}"
        return self._make_request('GET', endpoint)

    def create_comment(self, issue_iid: str, body: str) -> Dict:
        """Create a comment on a GitLab issue.

        Args:
            issue_iid: GitLab issue IID
            body: Comment body text

        Returns:
            Comment data dictionary

        Raises:
            Exception: If comment creation fails
        """
        endpoint = f"projects/{self.project_id}/issues/{issue_iid}/notes"
        payload = {"body": body}
        return self._make_request('POST', endpoint, payload)

    def upload_attachment(self, issue_iid: str, file_path: str, file_name: Optional[str] = None) -> Dict:
        """Upload an attachment to a GitLab issue.

        Args:
            issue_iid: GitLab issue IID
            file_path: Local file path to upload
            file_name: Optional custom file name

        Returns:
            Upload response dictionary

        Raises:
            Exception: If upload fails
        """
        endpoint = f"projects/{self.project_id}/uploads"
        with open(file_path, 'rb') as f:
            files = {'file': (file_name or file_path.split('/')[-1], f)}
            url = f"{self.base_url}/{endpoint}"
            response = self.session.post(url, files=files, timeout=30)
            response.raise_for_status()
            return response.json()

    def get_users(self, search: Optional[str] = None) -> List[Dict]:
        """Get GitLab project users.

        Args:
            search: Optional username/email search

        Returns:
            List of user dictionaries
        """
        endpoint = f"projects/{self.project_id}/users"
        params = {}
        if search:
            params['search'] = search

        url = f"{self.base_url}/{endpoint}"
        response = self.session.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def link_related_issue(self, issue_iid: str, target_issue_iid: str) -> Dict:
        """Link related issues.

        Args:
            issue_iid: Source issue IID
            target_issue_iid: Target issue IID to link

        Returns:
            Link response data
        """
        endpoint = f"projects/{self.project_id}/issues/{issue_iid}/links"
        payload = {"target_issue_iid": target_issue_iid}
        return self._make_request('POST', endpoint, payload)

    def search_issues(self, title_query: str, limit: int = 10) -> List[Dict]:
        """Search for issues in the project by title.

        Args:
            title_query: Title to search for
            limit: Maximum number of results

        Returns:
            List of issue dictionaries
        """
        endpoint = f"projects/{self.project_id}/issues"
        url = f"{self.base_url}/{endpoint}"
        logger = logging.getLogger(__name__)

        try:
            params = {'search': title_query, 'per_page': limit}
            response = self.session.get(url, params=params, timeout=15)

            # Log detailed information for non-200 responses
            if not response.ok:
                logger.error(f"GitLab API GET request failed: {url}")
                logger.error(f"Status Code: {response.status_code}")
                logger.error(f"Query Parameters: {params}")
                logger.error(f"Response Headers: {dict(response.headers)}")

                # Try to get response text safely
                try:
                    response_text = response.text
                    if response_text:
                        logger.error(f"Response Body: {response_text}")
                    else:
                        logger.error("Response Body: (empty)")
                except Exception as e:
                    logger.error(f"Failed to read response body: {str(e)}")

            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to search GitLab issues: {str(e)}")
            raise Exception(f"Failed to search GitLab issues: {str(e)}")