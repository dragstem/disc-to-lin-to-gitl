"""Linear API client for fetching issues from team MAU."""

import requests
import tempfile
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from src.config_manager import ConfigManager
from src.error_logger import ErrorLogger

class LinearClient:
    """Client for interacting with Linear GraphQL API."""

    def __init__(self, config: ConfigManager) -> None:
        """Initialize Linear client.

        Args:
            config: Configuration manager instance
        """
        self.api_key = config.linear_api_key
        self.logger = ErrorLogger(config)
        self.team_name = config.linear_team_name  # Use configured team name
        self._team_cache = {}  # Cache for team ID lookups
        self.base_url = "https://api.linear.app/graphql"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        })

    def _make_request(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Make GraphQL request to Linear API.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            JSON response data

        Raises:
            Exception: If request fails or rate limited
        """
        payload = {"query": query, "variables": variables or {}}
        try:
            response = self.session.post(self.base_url, json=payload, timeout=15)
            self.logger.log('debug', f"Linear API Request: {response.status_code}")
            self.logger.log('debug', f"Request payload: {payload}")

            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                raise Exception(f"GraphQL errors: {data['errors']}")
            return data
        except requests.HTTPError as e:
            # Add more context for HTTP errors
            try:
                error_data = e.response.json()
                error_msg = f"HTTP {e.response.status_code}: {error_data.get('message', e.response.text)}"
            except:
                error_msg = str(e)
            raise Exception(f"Linear API HTTP error: {error_msg}")
        except requests.RequestException as e:
            raise Exception(f"Linear API request failed: {str(e)}")

    def get_team_id(self, team_name: Optional[str] = None) -> Tuple[str, str]:
        """Fetch the team ID and key for specified team name.

        Args:
            team_name: Name of the team to find (uses configured team if None)

        Returns:
            Tuple of (team_id, team_key) where team_key is the short code (e.g., 'ABO')

        Raises:
            Exception: If team not found or multiple with same name
        """
        if team_name is None:
            team_name = self.team_name

        # Check cache first
        if team_name in self._team_cache:
            self.logger.log('debug', f"Using cached team ID for {team_name}")
            return self._team_cache[team_name]

        query = """
        query {
          teams {
            nodes {
              id
              name
              key
            }
          }
        }
        """
        data = self._make_request(query)
        teams = data.get("data", {}).get("teams", {}).get("nodes", [])
        matching_teams = [team for team in teams if team["name"] == team_name]
        if not matching_teams:
            raise Exception(f"Team '{team_name}' not found in Linear")
        if len(matching_teams) > 1:
            raise Exception(f"Multiple teams with name '{team_name}' found")
        team = matching_teams[0]
        # Cache the result
        self._team_cache[team_name] = (team["id"], team["key"])
        self.logger.log('debug', f"Cached team ID for {team_name}: {team['id']}")
        return team["id"], team["key"]

    def get_issues_since(self, team_id: str, since_timestamp: Optional[str] = None) -> List[Dict]:
        """Get issues from MAU team since specified timestamp with all displayable fields.

        Args:
            team_id: Linear team ID
            since_timestamp: ISO timestamp string (optional)

        Returns:
            List of issue dictionaries with comprehensive field data
        """
        query = """
        query TeamIssues($teamId: ID!) {
          issues(filter: { team: { id: { eq: $teamId } } }) {
            nodes {
              id
              identifier
              title
              description
              createdAt
              updatedAt
              assignee {
                id
                name
                email
              }
              labels {
                nodes {
                  id
                  name
                  color
                }
              }
              priority
              state {
                id
                name
              }
              dueDate
              estimate
              parent {
                id
                identifier
                title
              }
              attachments {
                nodes {
                  id
                  title
                  url
                }
              }
              comments {
                nodes {
                  id
                  body
                  createdAt
                  updatedAt
                }
              }
              children {
                nodes {
                  id
                  identifier
                  title
                }
              }
            }
          }
        }
        """
        variables = {"teamId": team_id}
        data = self._make_request(query, variables)
        issues = data.get("data", {}).get("issues", {}).get("nodes", [])

        if since_timestamp:
            cutoff = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
            issues = [issue for issue in issues if
                      datetime.fromisoformat(issue["updatedAt"].replace('Z', '+00:00')).replace(tzinfo=None) > cutoff]

        return issues

    def get_issues_since_by_team(self, team_name: str, since_timestamp: Optional[str] = None) -> List[Dict]:
        """Get all issues from specified team since timestamp.

        Args:
            team_name: Name of the team to query
            since_timestamp: ISO timestamp string (optional)

        Returns:
            List of issue dictionaries
        """
        team_id, team_key = self.get_team_id(team_name)
        issues = self.get_issues_since(team_id, since_timestamp)
        if since_timestamp:
            self.logger.log('debug', f"Fetched {len(issues)} issues updated since {since_timestamp} from Team '{team_name}' (ID: {team_id})")
        else:
            self.logger.log('debug', f"Fetched {len(issues)} total issues from Team '{team_name}' (ID: {team_id})")
        return issues

    def download_attachment(self, attachment_url: str, filename: str) -> str:
        """Download attachment from Linear and save to temporary file.

        Args:
            attachment_url: URL of the attachment to download
            filename: Original filename

        Returns:
            Path to the downloaded temporary file

        Raises:
            Exception: If download fails
        """
        try:
            response = self.session.get(attachment_url, timeout=30)
            response.raise_for_status()

            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix=f"_{filename}")
            with os.fdopen(temp_fd, 'wb') as temp_file:
                temp_file.write(response.content)

            return temp_path
        except requests.RequestException as e:
            raise Exception(f"Failed to download attachment from {attachment_url}: {str(e)}")

    def get_issue_details(self, issue_id: str) -> Optional[Dict]:
        """Get detailed information for a specific issue.

        Args:
            issue_id: Linear issue ID

        Returns:
            Issue details dictionary or None if not found
        """
        query = """
        query Issue($id: String!) {
          issue(id: $id) {
            id
            title
            description
            createdAt
            updatedAt
            assignee {
              name
            }
            labels {
              nodes {
                name
                color
              }
            }
          }
        }
        """
        try:
            data = self._make_request(query, {"id": issue_id})
            return data.get("data", {}).get("issue")
        except Exception as e:
            # Log error and return None for missing issues
            return None

    def create_issue(self, team_id: str, title: str, description: str = "", priority: int = 3, labels: Optional[List[str]] = None) -> Dict:
        """Create a new Linear issue.

        Args:
            team_id: Linear team ID
            title: Issue title
            description: Issue description
            priority: Issue priority (1-4)
            labels: List of label names

        Returns:
            Created issue dictionary

        Raises:
            Exception: If creation fails
        """
        mutation = """
        mutation IssueCreate($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue {
              id
              title
              identifier
              url
            }
          }
        }
        """

        variables = {
            "input": {
                "teamId": team_id,
                "title": title,
                "description": description,
                "priority": priority
            }
        }

        # Add labels if provided
        if labels:
            variables["input"]["labelIds"] = labels

        data = self._make_request(mutation, variables)
        result = data.get("data", {}).get("issueCreate", {})

        if not result.get("success"):
            raise Exception(f"Failed to create Linear issue: {result}")

        return result["issue"]

    def update_issue(self, issue_id: str, title: Optional[str] = None, description: Optional[str] = None,
                    priority: Optional[int] = None, labels: Optional[List[str]] = None) -> Dict:
        """Update an existing Linear issue.

        Args:
            issue_id: Linear issue ID
            title: New title (optional)
            description: New description (optional)
            priority: New priority (optional)
            labels: New list of label names (optional)

        Returns:
            Updated issue dictionary

        Raises:
            Exception: If update fails
        """
        mutation = """
        mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
          issueUpdate(id: $id, input: $input) {
            success
            issue {
              id
              title
              identifier
              url
            }
          }
        }
        """

        variables = {"id": issue_id, "input": {}}

        # Add fields that are provided (excluding state to avoid UUID issues)
        if title is not None:
            variables["input"]["title"] = title
        if description is not None:
            variables["input"]["description"] = description
        if priority is not None:
            variables["input"]["priority"] = priority
        if labels is not None:
            variables["input"]["labelIds"] = labels

        if not variables["input"]:
            raise Exception("No fields provided for update")

        data = self._make_request(mutation, variables)
        result = data.get("data", {}).get("issueUpdate", {})

        if not result.get("success"):
            raise Exception(f"Failed to update Linear issue: {result}")

        return result["issue"]

    def get_linear_issues_for_team_all_states(self, team_id: str) -> Dict[str, Dict]:
        """Get all Linear issues for a team (including backlog) with pagination.

        Args:
            team_id: Linear team ID

        Returns:
            Dictionary mapping issue titles to issue data
        """
        issues = {}
        query = """
        query Issues($teamId: ID!, $after: String) {
          issues(first: 100, after: $after, filter: {team: {id: {eq: $teamId}}}) {
            nodes {
              id
              title
              description
              state {
                id
                name
              }
              priority
              createdAt
              updatedAt
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
        """

        after = None
        while True:
            variables = {"teamId": team_id, "after": after}
            data = self._make_request(query, variables)
            nodes = data.get("data", {}).get("issues", {}).get("nodes", [])

            for issue in nodes:
                issues[issue["title"]] = issue

            page_info = data.get("data", {}).get("issues", {}).get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")

        self.logger.log('debug', f"Fetched {len(issues)} issues for team {team_id}")
        return issues