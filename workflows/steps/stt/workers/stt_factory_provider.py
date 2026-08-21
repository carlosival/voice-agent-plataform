'''
Factory for STT providers
'''

from workflows.steps.stt.workers.stt_provider_openai import call_stt
## TODO: Add more providers as needed

def get_stt_provider(provider_name: str):
    providers = {
        "openai": call_stt,
        # TODO: Add more providers as needed
    }

    provider = providers.get(provider_name, None)

    if provider:
        return provider
    else:
        raise ValueError(f"Unknown STT provider: {provider_name}")
