import logging
import httpx
import json
from typing import Generator

logger = logging.getLogger(__name__)


class LLM:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.Client(timeout=120.0)
        self.model = "llama-3.2-3b"
        self.warmed = False
        logger.info(f"LLM client configured for {base_url}")

    def warmup(self):
        if self.warmed:
            return
        logger.info("Warming up LLM...")
        try:
            response = self.client.post(
                f"{self.base_url}/completions",
                json={
                    "prompt": "Hello",
                    "max_tokens": 1,
                    "stream": False,
                },
            )
            if response.status_code == 200:
                self.warmed = True
                logger.info("LLM warmed up successfully")
            else:
                logger.warning(f"LLM warmup failed: {response.status_code}")
        except Exception as e:
            logger.warning(f"LLM warmup error: {e}")

    def generate(self, prompt: str, system_prompt: str = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "temperature": 0.7,
                "max_tokens": 256,
            },
        )
        if response.status_code != 200:
            logger.error(f"LLM error: {response.status_code} - {response.text}")
            return "Sorry, I encountered an error."

        result = response.json()
        return result["choices"][0]["message"]["content"]

    def generate_messages(self, messages: list, system_prompt: str = None) -> str:
        """Send a structured conversation history as separate role messages."""
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        response = self.client.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": full_messages,
                "stream": False,
                "temperature": 0.7,
                "max_tokens": 256,
            },
        )
        if response.status_code != 200:
            logger.error(f"LLM error: {response.status_code} - {response.text}")
            return "Sorry, I encountered an error."

        result = response.json()
        return result["choices"][0]["message"]["content"]

    def generate_streaming(self, prompt: str, system_prompt: str = None) -> Generator[str, None, None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        with self.client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "stream": True,
                "temperature": 0.7,
                "max_tokens": 256,
            },
        ) as response:
            if response.status_code != 200:
                logger.error(f"LLM streaming error: {response.status_code}")
                return

            for line in response.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
