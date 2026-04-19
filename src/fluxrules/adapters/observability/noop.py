class NoopTracer:
    def on_evaluation_start(self, ruleset_id: str) -> None:
        return None

    def on_evaluation_end(self, ruleset_id: str, matched_count: int) -> None:
        return None
