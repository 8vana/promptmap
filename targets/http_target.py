import json

import httpx

from engine.base_target import TargetAdapter


class HTTPTargetAdapter(TargetAdapter):
    """Sends prompts to an HTTP JSON endpoint. Stateless – conversation_id is ignored."""

    def __init__(
        self,
        endpoint: str,
        body_template: dict,
        response_key: str,
        timeout: float = 300.0,
    ):
        """
        endpoint      : POST URL of the target app (e.g. http://localhost:8000/chat)
        body_template : JSON body with "{PROMPT}" placeholder, e.g. {"text": "{PROMPT}"}
        response_key  : JSON key to extract the response text, e.g. "text"
        """
        self._endpoint = endpoint
        self._body_template = body_template
        self._response_key = response_key
        self._timeout = timeout

    async def send(self, prompt: str, conversation_id: str) -> str:
        body_str = json.dumps(self._body_template).replace("{PROMPT}", prompt)
        body = json.loads(body_str)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._endpoint, json=body)
            response.raise_for_status()
            data = response.json()

        if self._response_key not in data:
            raise KeyError(
                f"Response key '{self._response_key}' not found in: {list(data.keys())}"
            )
        return str(data[self._response_key])
