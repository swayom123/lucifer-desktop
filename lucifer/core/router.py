"""Deterministic capability routing with duplicate-ID rejection."""

from lucifer.agents.base import BaseAgent
from lucifer.core.planner import PlanTask


class AgentRouter:
    def __init__(self, agents: list[BaseAgent] | None = None) -> None:
        self._agents: dict[str, BaseAgent] = {}
        for agent in agents or []:
            self.register(agent)

    def register(self, agent: BaseAgent) -> None:
        identifier = agent.definition.id
        if identifier in self._agents:
            raise ValueError(f"duplicate agent ID: {identifier}")
        self._agents[identifier] = agent

    def route(self, task: PlanTask) -> BaseAgent | None:
        matches = [
            agent
            for agent in self._agents.values()
            if task.capability in agent.definition.capabilities
            and set(task.required_tools).issubset(agent.definition.allowed_tools)
        ]
        return min(matches, key=lambda agent: agent.definition.id) if matches else None
