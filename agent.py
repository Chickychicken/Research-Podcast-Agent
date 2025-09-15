from abc import ABC, abstractmethod
from typing import Any, Dict, List
from pydantic import BaseModel

class TaskResult(BaseModel):
    task_id: str
    task_description: str
    findings: str
    sources: List[str]
    confidence_score: float
    status: str

class BaseAgent(ABC):
    def __init__(self, agent_id: str, model_name: str = "gpt-4o-mini"):
        self.agent_id = agent_id
        self.model_name = model_name
        self.capabilities = []
    
    @abstractmethod
    async def execute_task(self, task: Dict[str, Any]) -> TaskResult:
        '''
        Asynchronous coroutine. This is an asynchronous way to process a given task dictionary and return a TaskResult
        
        Typical for operations that involve I/O, network requests, 
        or other potentially long-running tasks that shouldn't 
        block the main program execution. 
        '''
        pass

    @abstractmethod
    def can_handle_task(self, task_type: str) -> bool:
        '''Used in systems where different "handlers" or "workers" are responsible for specific types of tasks, 
        allowing a dispatcher to route tasks to the appropriate handler.
        '''
        pass