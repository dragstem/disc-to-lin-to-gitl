"""Discord API client for retrieving forum posts."""

import logging
import threading
import time
from typing import Dict, List, Optional
import requests
from src.config_manager import ConfigManager


class DiscordClient:
    """Client for interacting with Discord REST API."""

    def __init__(self, config: ConfigManager) -> None:
        """Initialize Discord client.

        Args:
            config: Configuration manager instance
        """
        self.bot_token = config.discord_bot_token
        self.guild_id = config.discord_guild_id
        self.forum_channel_id = config.discord_forum_channel_id
        self.base_url = config.discord_api_base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bot {self.bot_token}",
            "Content-Type": "application/json"
        })
        # Rate limiting: Discord allows 50 requests per second globally
        self.rate_limit_lock = threading.Lock()
        self.last_request_time = 0.0
        self.request_interval = 1.0 / 50.0  # 50 requests per second

    def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        logger = logging.getLogger(__name__)
        with self.rate_limit_lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.request_interval:
                sleep_time = self.request_interval - time_since_last
                logger.info(f"Rate limiting: sleeping {sleep_time} seconds")
                time.sleep(sleep_time)
            self.last_request_time = time.time()

    def _make_request(self, method: str, endpoint: str, payload: Optional[Dict] = None) -> Dict:
        """Make HTTP request to Discord API with rate limiting and error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            payload: Request payload (for POST/PUT)

        Returns:
            JSON response data

        Raises:
            Exception: If request fails
        """
        self._rate_limit()
        url = f"{self.base_url}/{endpoint}"
        logger = logging.getLogger(__name__)

        try:
            if method.upper() == 'POST':
                response = self.session.post(url, json=payload, timeout=15)
            elif method.upper() == 'GET':
                response = self.session.get(url, timeout=15)
            elif method.upper() == 'PUT':
                response = self.session.put(url, json=payload, timeout=15)
            elif method.upper() == 'PATCH':
                response = self.session.patch(url, json=payload, timeout=15)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 1))
                logger.warning(f"Rate limited by Discord API. Retrying after {retry_after} seconds.")
                time.sleep(retry_after)
                self.last_request_time = time.time() - self.request_interval
                return self._make_request(method, endpoint, payload)

            # Log detailed information for non-200 responses
            if not response.ok:
                logger.error(f"Discord API {method} request failed: {url}")
                logger.error(f"Status Code: {response.status_code}")
                logger.error(f"Response Headers: {dict(response.headers)}")

                try:
                    response_text = response.text
                    if response_text:
                        logger.error(f"Response Body: {response_text}")
                    else:
                        logger.error("Response Body: (empty)")
                except Exception as e:
                    logger.error(f"Failed to read response body: {str(e)}")

                if payload and method.upper() in ['POST', 'PUT', 'PATCH']:
                    logger.error(f"Request Payload: {payload}")
                logger.error(f"Request Headers: {dict(self.session.headers)}")

            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Discord API request failed: {str(e)}")
            raise Exception(f"Discord API request failed: {str(e)}")

    def get_forum_threads(self, limit: int = 100) -> List[Dict]:
        """Retrieve forum threads from the configured forum channel.

        Args:
            limit: Maximum number of threads to retrieve

        Returns:
            List of thread dictionaries
        """
        logger = logging.getLogger(__name__)
        logger.info(f"Retrieving active forum threads from channel {self.forum_channel_id}")

        try:
            endpoint = f"channels/{self.forum_channel_id}/threads/active"
            params = {"limit": limit}
            url = f"{self.base_url}/{endpoint}"

            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            threads = data.get('threads', [])

            # Add available_tags from channel to each thread
            channel = self.get_channel_info()
            available_tags = channel.get('available_tags', [])
            for thread in threads:
                thread['available_tags'] = available_tags

            logger.info(f"Retrieved {len(threads)} active forum threads")
            return threads
        except requests.RequestException as e:
            logger.error(f"Failed to retrieve active forum threads: {str(e)}")
            raise Exception(f"Failed to retrieve forum threads: {str(e)}")

    def get_archived_threads(self, limit: int = 100) -> List[Dict]:
        """Retrieve all archived threads from the forum channel.

        Args:
            limit: Maximum number of threads to retrieve per request

        Returns:
            List of archived thread dictionaries
        """
        logger = logging.getLogger(__name__)
        logger.info(f"Retrieving archived threads from channel {self.forum_channel_id}")

        try:
            endpoint = f"channels/{self.forum_channel_id}/threads/archived/public"
            all_threads = []
            after = None
            has_more = True

            while has_more:
                params = {"limit": limit}
                if after:
                    params["after"] = after

                url = f"{self.base_url}/{endpoint}"
                response = self.session.get(url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()

                threads = data.get("threads", [])
                all_threads.extend(threads)
                has_more = data.get("has_more", False)

                if threads:
                    after = threads[-1].get('thread_metadata', {}).get('archive_timestamp')

            # Add available_tags from channel to each thread
            channel = self.get_channel_info()
            available_tags = channel.get('available_tags', [])
            for thread in all_threads:
                thread['available_tags'] = available_tags

            logger.info(f"Retrieved {len(all_threads)} archived threads")
            return all_threads
        except requests.RequestException as e:
            logger.error(f"Failed to retrieve archived threads: {str(e)}")
            raise Exception(f"Failed to retrieve archived threads: {str(e)}")

    def get_thread_messages(self, thread_id: str, limit: int = 100) -> List[Dict]:
        """Retrieve messages from a specific thread.

        Args:
            thread_id: Discord thread ID
            limit: Maximum number of messages to retrieve

        Returns:
            List of message dictionaries
        """
        logger = logging.getLogger(__name__)
        logger.info(f"Retrieving messages from thread {thread_id}")

        try:
            endpoint = f"channels/{thread_id}/messages"
            params = {"limit": limit}
            url = f"{self.base_url}/{endpoint}"

            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            messages = response.json()

            logger.info(f"Retrieved {len(messages)} messages from thread {thread_id}")
            return messages
        except requests.RequestException as e:
            logger.error(f"Failed to retrieve thread messages: {str(e)}")
            raise Exception(f"Failed to retrieve thread messages: {str(e)}")

    def test_connectivity(self) -> bool:
        """Test connectivity to Discord API.

        Returns:
            True if connection successful, False otherwise
        """
        logger = logging.getLogger(__name__)
        logger.info("Testing Discord API connectivity")

        try:
            # Simple test: get current user (bot)
            endpoint = "users/@me"
            self._make_request('GET', endpoint)
            logger.info("Discord API connectivity test successful")
            return True
        except Exception as e:
            logger.error(f"Discord API connectivity test failed: {str(e)}")
            return False

    def get_channel_info(self, channel_id: Optional[str] = None) -> Dict:
        """Get information about a Discord channel.

        Args:
            channel_id: Channel ID to get info for (defaults to forum channel)

        Returns:
            Channel information dictionary
        """
        channel_id = channel_id or self.forum_channel_id
        endpoint = f"channels/{channel_id}"
        return self._make_request('GET', endpoint)