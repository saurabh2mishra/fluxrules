"""Reproducible, CI-gated scale readiness test.

This test converts the previously *unproven* scale claim ("millions of facts
evaluated against 1,000+ rules") into a collected, asserted, CI-gated proof.

Unlike the ``perf_*.py`` scripts in this directory (which execute at module
import scope and are **not** collected by pytest), this is a real
``@pytest.mark.performance`` test. It is picked up by the isolated, serial
performance job (``pytest tests/ -m performance -p no:xdist``) and therefore
runs in CI.

What it proves
--------------
1. **Scale.** A single ``PhreakEngine`` streams ``FACTS`` (default 1,000,000)
   distinct facts against ``RULES`` (default 1,200 > 1,000) loaded rules and
   completes without error.
2. **Correctness at that scale.** For a representative sample of the same
   facts, PHREAK's *complete* fired-rule-id set is compared for exact equality
   against the dependency-free :class:`ReferenceEvaluator` oracle. This is a
   full per-fact set comparison (not a sampled subset of rule ids).
3. **Throughput budget.** Sustained throughput must stay above a conservative
   floor, so a performance regression fails the gate instead of silently
   degrading.
4. **Bounded memory.** Peak resident set size must stay under a ceiling, so a
   memory leak across the stream fails the gate.

Scale and budgets are environment-overridable so contributors can run a fast
local smoke check, while CI proves the full advertised scale by default::

    FLUXRULES_SCALE_FACTS=20000 FLUXRULES_SCALE_RULES=1200 \
        pytest tests/performance/test_scale_readiness.py -m performance -p no:xdist -s
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import resource
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fluxrules.domain.models import Ruleset
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.services.reference_evaluator import ReferenceEvaluator

# Configuration (env-overridable; defaults prove the advertised scale)

FACTS = int(os.environ.get("FLUXRULES_SCALE_FACTS", "1000000"))
RULES = int(os.environ.get("FLUXRULES_SCALE_RULES", "1200"))
CONDITIONS_PER_RULE = int(os.environ.get("FLUXRULES_SCALE_CONDITIONS", "5"))
FIELD_SPACE = int(os.environ.get("FLUXRULES_SCALE_FIELDS", "60"))
# Facts to validate for full fired-set equality against the reference oracle.
CORRECTNESS_SAMPLE = int(os.environ.get("FLUXRULES_SCALE_SAMPLE", "2000"))
# Conservative floor: shared CI runners are far slower than a dev laptop.
MIN_THROUGHPUT_FPS = float(os.environ.get("FLUXRULES_SCALE_MIN_FPS", "150"))
# Generous ceiling: catches a genuine leak without flaking on runner variance.
MAX_PEAK_RSS_MB = float(os.environ.get("FLUXRULES_SCALE_MAX_RSS_MB", "2048"))

RULE_SEED = 42
FACT_SEED = 7
ARTIFACT_PATH = os.environ.get("FLUXRULES_SCALE_ARTIFACT")


def _and_rule(rid: int, rng: random.Random) -> object:
    from fluxrules import Rule

    n = min(CONDITIONS_PER_RULE, FIELD_SPACE)
    fields = rng.sample(range(FIELD_SPACE), n)
    conditions = [
        {
            "type": "condition",
            "field": f"field_{f}",
            "op": rng.choice([">", ">=", "<", "<=", "==", "!="]),
            "value": rng.randint(0, 1000),
        }
        for f in fields
    ]
    # Mix boolean shapes so the at-scale oracle check exercises OR / NOT /
    # nesting, not just flat AND. Every referenced field is always present in
    # the generated facts, so this stays clear of the negation-over-absent-field
    # divergence tracked in tests/engine/test_differential_fuzz.py.
    shape = rng.choice(["and", "and", "or", "not_and"])
    if shape == "or":
        dsl = {"type": "or", "conditions": conditions}
    elif shape == "not_and":
        head, *rest = conditions
        dsl = {"type": "and", "conditions": [{"type": "not", "conditions": [head]}, *rest]}
    else:
        dsl = {"type": "and", "conditions": conditions}
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl=dsl,
        priority=rid % 10,
        domain=f"d{rid % 5}",
        tags=frozenset([f"tag_{rid % 3}"]),
        persist=False,
    )


def _build_rules() -> list[object]:
    rng = random.Random(RULE_SEED)
    return [_and_rule(i, rng) for i in range(RULES)]


def _make_fact(rng: random.Random) -> dict[str, int]:
    return {f"field_{i}": rng.randint(0, 1000) for i in range(FIELD_SPACE)}


def _peak_rss_mb() -> float:
    """Peak resident set size in MB, normalised across platforms."""
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports kilobytes.
    if sys.platform == "darwin":
        return ru / (1024 * 1024)
    return ru / 1024


def _checkout_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _write_artifact(
    *,
    elapsed: float,
    throughput: float,
    peak_rss_mb: float,
    total_fired: int,
    correctness_digest: str,
) -> None:
    if not ARTIFACT_PATH:
        return

    artifact = {
        "commit": _checkout_commit(),
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "os": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "workload": {
            "facts": FACTS,
            "rules": RULES,
            "conditions_per_rule": CONDITIONS_PER_RULE,
            "field_space": FIELD_SPACE,
            "correctness_sample": CORRECTNESS_SAMPLE,
            "rule_seed": RULE_SEED,
            "fact_seed": FACT_SEED,
        },
        "correctness": {
            "oracle": "ReferenceEvaluator",
            "comparison": "complete fired-rule-id set per sampled fact",
            "sample_digest_sha256": correctness_digest,
        },
        "performance": {
            "engine": "PhreakEngine(stateless)",
            "elapsed_seconds": elapsed,
            "throughput_facts_per_second": throughput,
            "total_fired": total_fired,
            "peak_rss_mb": peak_rss_mb,
            "min_throughput_facts_per_second": MIN_THROUGHPUT_FPS,
            "max_peak_rss_mb": MAX_PEAK_RSS_MB,
        },
    }
    path = Path(ARTIFACT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")


@pytest.mark.performance
def test_scale_readiness_million_facts_thousand_rules() -> None:
    assert RULES > 1000, "scale claim requires more than 1,000 rules"
    assert FACTS >= 1_000_000 or "FLUXRULES_SCALE_FACTS" in os.environ, (
        "default run must stream at least 1,000,000 facts to prove the claim"
    )

    rules = _build_rules()

    # 1) Correctness at scale: PHREAK's full fired set must equal the
    #    independent reference oracle for every sampled fact.
    reference = ReferenceEvaluator()
    ruleset = Ruleset(group="scale", rules=tuple(r.to_engine_rule() for r in rules))

    verify_engine = PhreakEngine(streaming_mode=False)
    verify_engine.load_rules(rules)

    sample_rng = random.Random(FACT_SEED)
    correctness_digest = hashlib.sha256()
    for _ in range(CORRECTNESS_SAMPLE):
        fact = _make_fact(sample_rng)
        phreak_fired = set(verify_engine.evaluate(fact).fired_rules)
        reference_matched = set(reference.evaluate(ruleset, fact).fired_rules)
        assert phreak_fired == reference_matched, (
            "PHREAK and the reference evaluator disagreed on the fired-rule set"
        )
        correctness_digest.update(
            json.dumps(
                {
                    "fact": fact,
                    "fired": sorted(phreak_fired),
                    "matched": sorted(reference_matched),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )

    # 2) Scale + throughput + memory: stream the full fact volume through one
    #    engine. Facts are generated inline so the stream itself does not hold
    #    a million dicts in memory.
    engine = PhreakEngine(streaming_mode=False)
    engine.load_rules(rules)

    fact_rng = random.Random(FACT_SEED + 1)
    total_fired = 0
    start = time.perf_counter()
    for _ in range(FACTS):
        result = engine.evaluate(_make_fact(fact_rng))
        total_fired += len(result.fired_rules)
    elapsed = time.perf_counter() - start

    throughput = FACTS / elapsed
    peak_rss_mb = _peak_rss_mb()

    print(
        f"\n[scale] facts={FACTS:,} rules={RULES:,} "
        f"elapsed={elapsed:.1f}s throughput={throughput:,.0f} facts/s "
        f"total_fired={total_fired:,} peak_rss={peak_rss_mb:.0f}MB"
    )

    assert throughput >= MIN_THROUGHPUT_FPS, (
        f"throughput {throughput:,.0f} facts/s fell below the {MIN_THROUGHPUT_FPS} floor"
    )
    assert peak_rss_mb <= MAX_PEAK_RSS_MB, (
        f"peak RSS {peak_rss_mb:.0f}MB exceeded the {MAX_PEAK_RSS_MB}MB ceiling"
    )
    _write_artifact(
        elapsed=elapsed,
        throughput=throughput,
        peak_rss_mb=peak_rss_mb,
        total_fired=total_fired,
        correctness_digest=correctness_digest.hexdigest(),
    )
