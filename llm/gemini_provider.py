from google import genai
from google.genai import types
from dotenv import load_dotenv
import json
import os

from llm.base import LLMProvider, validate_test_suite


class GeminiProvider(LLMProvider):
    def __init__(self):
        self._client = None
        self._configured = None

    def _ensure_client(self):
        if self._configured is not None:
            return
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        self._configured = bool(api_key)
        self._client = genai.Client(api_key=api_key) if api_key else None

    def is_configured(self) -> bool:
        self._ensure_client()
        return self._client is not None

    def list_models(self) -> list[list[str]]:
        if not self.is_configured():
            return []
        models = self._client.models.list()
        result = []
        blocked_terms = (
            "embedding",
            "imagen",
            "image",
            "veo",
            "tts",
            "speech",
            "audio",
            "banana",
        )
        for model in models:
            name = getattr(model, "name", "")
            lower_name = name.lower()
            if any(term in lower_name for term in blocked_terms):
                continue
            result.append([model.name, model.display_name])
        return sorted(result)

    def generate_result(self, model, prompt, require_happy_path=True):
        if not self.is_configured():
            return {"error": "API key in .env file not set"}

        try:
            response = self._client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )

            data = json.loads(response.text)
            if not isinstance(data, dict):
                return {"error": "Model returned JSON that is not an object", "raw": response.text}

            if "endpoints" not in data and "endpoint" in data:
                data["endpoints"] = [data["endpoint"]]

            ok, err = validate_test_suite(data, require_happy_path=require_happy_path)
            if ok:
                return data

            return {"error": err, "raw": response.text}

        except json.JSONDecodeError:
            return {
                "error": "Model returned invalid JSON",
                "raw": getattr(response, "text", ""),
            }

        except Exception as e:
            return {"error": str(e)}
