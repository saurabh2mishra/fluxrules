from app.database import SessionLocal, init_db
from app.models.rule import Rule
from app.services.rule_service import RuleService
from app.schemas.rule import RuleCreate
import json

# Initialize database
init_db()

db = SessionLocal()

try:
    # Create a simple test rule
    rule_data = RuleCreate(
        name="Debug Test Rule",
        description="Testing rule creation",
        group="test",
        priority=10,
        enabled=True,
        condition_dsl={
            "type": "condition",
            "field": "amount",
            "op": ">",
            "value": 100
        },
        action="print('test')"
    )
    
    print("Creating rule...")
    service = RuleService(db)
    rule = service.create_rule(rule_data, user_id=1)
    
    print(f"✓ Rule created successfully!")
    print(f"  ID: {rule.id}")
    print(f"  Name: {rule.name}")
    print(f"  Condition: {rule.condition_dsl}")
    
except Exception as e:
    print(f"✗ Error creating rule:")
    print(f"  {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

finally:
    db.close()
