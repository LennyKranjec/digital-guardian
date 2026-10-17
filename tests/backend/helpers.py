"""Paralleltest-Helfer: dieselbe Aktion gleichzeitig ausführen und alle Ergebnisse einsammeln.

Beispiel (zwei gleichzeitige Statuswechsel): `results = run_parallel(lambda: client.post(...), 2)`.
Ergebnisse stehen in Startreihenfolge; Ausnahmen werden nicht verschluckt, sondern erneut ausgelöst.
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


def run_parallel[T](action: Callable[[], T], workers: int) -> list[T]:
    """Startet `workers` Threads an einer Barriere (möglichst gleichzeitiger Start)."""
    barrier = threading.Barrier(workers)

    def task() -> T:
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(task) for _ in range(workers)]
        return [future.result(timeout=30) for future in futures]
