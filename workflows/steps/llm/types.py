import dataclasses

@dataclasses.dataclass
class LLMEvent:
    event: str
    data: str
    