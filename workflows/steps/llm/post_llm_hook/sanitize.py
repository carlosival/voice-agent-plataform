'''
Sanitize LLM response
'''

from yaafpy.types import ExecContext, Middleware
from workflows.utils.sanitize_sentences import sanitize_sentence
from workflows.utils.sanitize_sentences import sanitize_sentence

async def sanitize(input: str , ctx: ExecContext) -> str:

    return sanitize_sentence(input)
    