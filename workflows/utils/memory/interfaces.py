
from typing import Protocol, List, Dict

class IMemory(Protocol):
    
    async def add_user_message(self, message: str)-> bool:
        ...
        
    async def add_ai_message(self,message: str, action: str )-> bool:
        ...
        

    async def add_tools_results(self, result: str, tool_call_id: str)-> bool:
        ...

    async def get_messages(self) -> List[Dict[str, str]]:
        ...
