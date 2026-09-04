from llm.gemini_provider import GeminiProvider
from llm.qa6_llm_provider import QA6Provider

providers = {
        "gemini": GeminiProvider,
        "qa6 llm": QA6Provider,
        }

def get_provider(provider_name: str):
    name = provider_name.lower()
    prov_class = providers.get(name)
    if prov_class is None:
        raise ValueError(f"unknown provider: {provider_name}")
    return prov_class()

def get_avl_providers() -> list[str]:
    return [prov.title() for prov in list(providers.keys())]
