from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from app.models.conflicted_rule import ConflictedRule
from app.models.rule import Rule
from app.config import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def cleanup_orphaned_conflicts():
    session = SessionLocal()
    try:
        all_conflicts = session.query(ConflictedRule).all()
        deleted = 0
        for conflict in all_conflicts:
            orphan = False
            # Check conflicting_rule_id
            if conflict.conflicting_rule_id:
                rule = session.query(Rule).filter(Rule.id == conflict.conflicting_rule_id).first()
                if not rule:
                    orphan = True
            # Check new_rule_id (if used)
            if conflict.new_rule_id:
                rule = session.query(Rule).filter(Rule.id == conflict.new_rule_id).first()
                if not rule:
                    orphan = True
            if orphan:
                print(f"Deleting orphaned conflict id={conflict.id} (references missing rule)")
                session.delete(conflict)
                deleted += 1
        session.commit()
        print(f"Cleanup complete. Deleted {deleted} orphaned conflict(s).")
    finally:
        session.close()

if __name__ == "__main__":
    cleanup_orphaned_conflicts()
