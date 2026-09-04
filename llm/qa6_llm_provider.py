import json

import requests

from llm.base import LLMProvider, validate_test_suite

models = [["gpt-4o-mini-2024-07-18", "GPT 4o Mini"], ["gpt-5.1-2025-11-13", "GPT 5.1"]]


def _extract_message_content(payload):
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    return content if isinstance(content, str) else None


class QA6Provider(LLMProvider):
    def __init__(self):
        pass

    def is_configured(self):
        return True

    def list_models(self):
        return models

    def generate_result(self, model, prompt, require_happy_path=True):
        url = "http://qa6-intuitionx-llm-router-v2.sprinklr.com/chat-completion"
        kwargs = {
            "headers": {"Content-Type": "application/json"},
            "json": {
                "model": model,
                "provider": "AZURE_OPEN_AI",
                "partner_id": 66000000,
                "client_identifier": "backend-platform-dev",
                "tracking_params": {
                    "feature": "PR_AGENT_CODE_REVIEW",
                },
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            },
        }

        content = ""
        try:
            res = requests.post(url, timeout=60, **kwargs)
            res.raise_for_status()
            payload = res.json()
            if not isinstance(payload, dict):
                return {"error": "QA6 returned JSON that is not an object"}
            if payload.get("error"):
                return {"error": str(payload["error"]), "raw": json.dumps(payload)}

            content = _extract_message_content(payload)
            if not content:
                return {
                    "error": "QA6 response missing choices[0].message.content",
                    "raw": json.dumps(payload),
                }

            data = json.loads(content)
            if not isinstance(data, dict):
                return {"error": "QA6 model returned JSON that is not an object", "raw": content}
            if "endpoints" not in data and "endpoint" in data:
                data["endpoints"] = [data["endpoint"]]

            ok, err = validate_test_suite(data, require_happy_path=require_happy_path)
            if ok:
                return data
            return {"error": err, "raw": content}
        except requests.RequestException as e:
            return {"error": f"QA6 request failed: {e}"}
        except json.JSONDecodeError as e:
            return {"error": f"QA6 returned invalid JSON: {e}", "raw": content}
        except Exception as e:
            return {"error": f"QA6 provider failed: {e}"}
