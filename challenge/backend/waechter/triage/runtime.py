"""Laufzeit-Bündel je Profil: kompiliert, verifiziert, mit Regelkarte (Vertrag §4, Hooks H3/H4).

`runtime_for` kompiliert beim ersten Zugriff und verifiziert dabei (V1 inklusive ungekürztem Gitter,
V3, V4). Ergibt die Verifikation nicht 0/0/0, wird `VerificationError` geworfen - es gibt keinen
stillen Rückfall auf den Lehrer. Das Ergebnis wird je (Wissensbasis-Hash, Profil-ID, Compiler-
Version) einmal je Prozess gehalten.
"""

import threading
from dataclasses import dataclass
from typing import Final

from waechter.triage import compiler
from waechter.triage.engine import CompiledEngine, TeacherEngine
from waechter.triage.kb import KnowledgeBase, ResolvedComposition, canonical_hash
from waechter.triage.verify import VerificationReport, require_clean, verify_composition


@dataclass(frozen=True, eq=False)
class ProfileRuntime:
    composition: ResolvedComposition
    compiled: tuple[compiler.CompiledComponent, ...]
    engine: CompiledEngine
    teacher: TeacherEngine
    report: VerificationReport
    tree_version: str
    rules: tuple[compiler.RenderedRule, ...]


_CACHE: Final[dict[tuple[str, str, str, bool], ProfileRuntime]] = {}
_LOCK: Final = threading.Lock()  # gleichzeitige Anfragen kompilieren ein Profil nur einmal


def runtime_for(kb: KnowledgeBase, profile_id: str, *, full_check: bool = True) -> ProfileRuntime:
    """Kompilat, Verifikationsbericht und Regelkarte eines Profils (Cache je KB-Hash).

    `full_check` gehört zum Schlüssel: ein Aufruf ohne ungekürzte Prüfung darf keinen schwächeren
    Bericht an einen Aufruf mit voller Prüfung weitergeben (A3 T-15 F-02).
    """
    key = (kb.hash, profile_id, compiler.COMPILER_VERSION, full_check)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            cached = _build(kb, profile_id, full_check)
            _CACHE[key] = cached
        return cached


def _build(kb: KnowledgeBase, profile_id: str, full_check: bool) -> ProfileRuntime:
    composition = kb.resolve(profile_id)
    compiled = tuple(compiler.compile_component(c) for c in composition.components)
    report = require_clean(verify_composition(composition, compiled, uncompressed=full_check))
    rules = tuple(
        rule
        for component, built in zip(composition.components, compiled, strict=True)
        for rule in compiler.render_rules(component, built)
    )
    return ProfileRuntime(
        composition=composition,
        compiled=compiled,
        engine=CompiledEngine(composition, compiled),
        teacher=TeacherEngine(composition),
        report=report,
        tree_version=canonical_hash([c.hash for c in compiled]),
        rules=rules,
    )
