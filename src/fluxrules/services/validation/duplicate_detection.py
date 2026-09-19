from fluxrules.services.compilation.rule_compiler import CompiledRule


class DuplicateDetector:
    """Detects rules with identical conditions."""

    def detect(self, compiled_rules: list[CompiledRule]) -> list[dict]:
        seen: dict[str, CompiledRule] = {}
        duplicates = []
        for rule in compiled_rules:
            cond = str(rule.source_condition)
            if cond in seen:
                duplicates.append(
                    {
                        "rule1_id": seen[cond].id,
                        "rule2_id": rule.id,
                        "rule1_name": seen[cond].name,
                        "rule2_name": rule.name,
                        "description": f"Duplicate condition between '{seen[cond].name}' (ID: {seen[cond].id}) and '{rule.name}' (ID: {rule.id})",
                    }
                )
            else:
                seen[cond] = rule
        return duplicates
