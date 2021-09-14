from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Generator

from domain.geo import Coordinates
from domain.types import IP, AgentID

logger = logging.getLogger(__name__)


@dataclass
class Agent:
    id: AgentID = AgentID()
    ip: IP = IP()
    name: str = ""
    alias: str = ""
    coords: Coordinates = Coordinates()


class Agents:
    def __init__(self) -> None:
        self._agents: Dict[AgentID, Agent] = {}
        self._agents_by_name: Dict[str, Agent] = {}

    def equals(self, other: Agents) -> bool:
        return sorted(self._agents.keys()) == sorted(other._agents.keys())

    def get_by_id(self, agent_id: AgentID) -> Agent:
        return self._agents.get(agent_id, Agent())

    def get_by_name(self, name: str) -> Agent:
        return self._agents_by_name.get(name, Agent())

    def insert(self, agent: Agent) -> None:
        self._agents[agent.id] = agent
        existing = self._agents_by_name.get(agent.name)
        if existing:
            logger.warning("Duplicate agent name '%s' (ids: %s %s)", agent.name, existing.id, agent.id)
            _dedup_name = "{agent.name} [{agent.id}]"
            del self._agents_by_name[existing.name]
            existing.name = _dedup_name.format(agent=existing)
            self._agents_by_name[existing.name] = existing
            agent.name = _dedup_name.format(agent=agent)
        self._agents_by_name[agent.name] = agent
        logger.debug("adding agent: id: %s name: %s alias: %s", agent.id, agent.name, agent.alias)

    def remove(self, agent: Agent):
        try:
            del self._agents[agent.id]
        except KeyError:
            logger.warning("Agent id: %s name: %s was not in dict by id", agent.id, agent.name)
        try:
            del self._agents_by_name[agent.name]
        except KeyError:
            logger.warning("Agent id: %s name: %s was not in dict by name", agent.id, agent.name)

    def all(self, reverse: bool = False) -> Generator[Agent, None, None]:
        for n in sorted(self._agents_by_name.keys(), key=lambda x: x.lower(), reverse=reverse):
            yield self._agents_by_name[n]

    def update_names_aliases(self, src: Agents) -> None:
        """
        Update agent names and aliases based on row data while preserving other existing agent attributes
        NOTE: This is an ugly hack that should be removed as soon as Kentik API becomes little bit more consistent
        """
        logger.debug("update_names_aliases: src_agents: %d", src.count)
        for src_agent in src.all():
            agent = self.get_by_id(src_agent.id)
            logger.debug("Updating agent id: %s (old name: %s new name: %s)", agent.id, agent.name, src_agent.name)
            if agent.id == AgentID():
                agent = src_agent
                logging.warning("Agent %s (name: %s) was not in cache", agent.id, agent.name)
                self.insert(agent)
            else:
                # We need to preserve other attributes retrieved from AgentsList, so we cannot simply replace the
                # existing agent. However, we need to delete it from the cache and re-insert it in order to
                # keep dictionary by name in sync
                self.remove(agent)
                agent.name = src_agent.name
                agent.alias = src_agent.alias
                self.insert(agent)

    @property
    def count(self) -> int:
        return len(self._agents)
