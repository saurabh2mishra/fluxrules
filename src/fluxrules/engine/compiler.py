"""Simple ruleset compiler/optimizer placeholder."""

from fluxrules.domain.models import Rule, Ruleset


class RuleCompiler:
    def compile(self, ruleset: Ruleset) -> Ruleset:
        ordered = tuple(sorted(ruleset.rules, key=lambda r: (r.priority, r.id), reverse=True))
        return Ruleset(id=ruleset.id, rules=ordered)
