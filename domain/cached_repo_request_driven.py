import logging
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from domain.model.mesh_results import MeshResults
from domain.repo import Repo
from domain.types import TestID

logger = logging.getLogger(__name__)


class CachedRepoRequestDriven:
    """
    CachedRepoRequestDriven allows for automatic, thread-safe cached data updates
    when the data is requested and cache is older than 'max_data_age_seconds'
    """

    TIMESTAMP_NEVER_UPDATED = datetime(year=1970, month=1, day=1, tzinfo=timezone.utc)

    def __init__(
        self,
        source_repo: Repo,
        monitored_test_id: TestID,
        max_data_age_seconds: int,
        lookback_seconds: int,
    ) -> None:
        self._source_repo = source_repo
        self._test_id = monitored_test_id
        self._max_data_age_seconds = max_data_age_seconds
        self._lookback_seconds = lookback_seconds
        self._cache_test_results = MeshResults(self.TIMESTAMP_NEVER_UPDATED)
        self._cache_access_lock = threading.Lock()

    def get_mesh_test_results(self) -> MeshResults:
        self._update_cache_if_needed()
        with self._cache_access_lock:
            return deepcopy(self._cache_test_results)

    def _update_cache_if_needed(self) -> None:
        if self._cached_data_fresh_enough():
            return

        logger.debug("Updating data cache start...")
        try:
            results = self._source_repo.get_mesh_test_results(self._test_id, self._lookback_seconds)
            with self._cache_access_lock:
                self._cache_test_results = results
            logger.debug("Updating data cache successful")
        except Exception as err:
            logger.exception("Updating data cache error")

    def _cached_data_fresh_enough(self) -> bool:
        max_age = timedelta(seconds=self._max_data_age_seconds)
        with self._cache_access_lock:
            return datetime.now(timezone.utc) - self._cache_test_results.utc_timestamp <= max_age
