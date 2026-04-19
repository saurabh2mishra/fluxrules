"""SQLAlchemy adapter placeholder shipped behind the sql extra."""


class SqlAlchemyRulesetRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save(self, ruleset):
        raise NotImplementedError("Install fluxrules[sql] and implement persistence mapping")

    def get(self, ruleset_id: str):
        raise NotImplementedError("Install fluxrules[sql] and implement persistence mapping")
