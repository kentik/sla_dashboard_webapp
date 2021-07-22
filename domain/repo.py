from typing import Optional, Protocol, Tuple

from domain.model.mesh_results import MeshResults
from domain.types import TestID


class Repo(Protocol):
    """Repo provides data access to Kentik Synthetic Tests"""

    def get_mesh_test_results(self, test_id: TestID, results_lookback_seconds: int) -> MeshResults:
        pass
