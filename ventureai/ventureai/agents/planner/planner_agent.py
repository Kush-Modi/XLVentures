from typing import Dict, Any
from core.registry.base import BaseAgent

class PlannerAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "planner"

    @property
    def description(self) -> str:
        return "Planner agent that determines the required specialist agents and generates the execution plan."

    @property
    def required_inputs(self) -> list[str]:
        return ["candidate_id"]

    @property
    def produced_outputs(self) -> list[str]:
        return ["planner_tasks", "planner_reasoning"]

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        candidate_id = state.get("candidate_id")
        
        # Static task plan mapping agents and requirement settings
        tasks = [
            {"agent": "candidate", "required": True},
            {"agent": "client", "required": True},
            {"agent": "knowledge", "required": True},
            {"agent": "action", "required": True},
        ]
        
        reasoning = f"Generated static execution plan for candidate ID '{candidate_id}' consisting of Candidate, Client, Knowledge, and Action agents."
        
        return {
            "planner_tasks": tasks,
            "planner_reasoning": reasoning
        }
