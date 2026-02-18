cd backend

cat > app/services/auth_service.py << 'ENDOFFILE'
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.models.user import User
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt
ENDOFFILE

# Ensure __init__.py exists
touch app/services/__init__.py

# Test the import
uv run python -c "from app.services.auth_service import authenticate_user, create_access_token, get_password_hash; print('✓ auth_service')"

# Now let's also verify and recreate all service files to be safe
cat > app/services/audit_service.py << 'ENDOFFILE'
from sqlalchemy.orm import Session
from app.models.audit import AuditLog
from typing import Optional
from datetime import datetime

class AuditService:
    def __init__(self, db: Session):
        self.db = db
    
    def log_action(
        self,
        action_type: str,
        entity_type: str,
        entity_id: Optional[int],
        user_id: Optional[int],
        details: str,
        execution_time: Optional[float] = None
    ):
        log = AuditLog(
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            details=details,
            execution_time=execution_time
        )
        self.db.add(log)
        self.db.commit()
ENDOFFILE

cat > app/services/conflict_detector.py << 'ENDOFFILE'
from sqlalchemy.orm import Session
from app.models.rule import Rule
from typing import List, Dict, Any
import json

class ConflictDetector:
    def __init__(self, db: Session):
        self.db = db
    
    def detect_all_conflicts(self) -> Dict[str, Any]:
        rules = self.db.query(Rule).filter(Rule.enabled == True).all()
        
        conflicts = []
        conflicts.extend(self._detect_duplicate_conditions(rules))
        conflicts.extend(self._detect_priority_collisions(rules))
        
        return {"conflicts": conflicts}
    
    def _detect_duplicate_conditions(self, rules: List[Rule]) -> List[Dict[str, Any]]:
        conflicts = []
        condition_map = {}
        
        for rule in rules:
            condition_str = rule.condition_dsl
            if condition_str in condition_map:
                conflicts.append({
                    "type": "duplicate_condition",
                    "rule1_id": condition_map[condition_str],
                    "rule2_id": rule.id,
                    "description": f"Rules {condition_map[condition_str]} and {rule.id} have identical conditions"
                })
            else:
                condition_map[condition_str] = rule.id
        
        return conflicts
    
    def _detect_priority_collisions(self, rules: List[Rule]) -> List[Dict[str, Any]]:
        conflicts = []
        priority_map = {}
        
        for rule in rules:
            key = (rule.group or "default", rule.priority)
            if key in priority_map:
                priority_map[key].append(rule.id)
            else:
                priority_map[key] = [rule.id]
        
        for (group, priority), rule_ids in priority_map.items():
            if len(rule_ids) > 1:
                conflicts.append({
                    "type": "priority_collision",
                    "group": group,
                    "priority": priority,
                    "rule_ids": rule_ids,
                    "description": f"Multiple rules in group '{group}' have priority {priority}"
                })
        
        return conflicts
ENDOFFILE

# Test all service imports
echo "Testing service imports..."
uv run python -c "from app.services.auth_service import authenticate_user; print('✓ auth_service')"
uv run python -c "from app.services.audit_service import AuditService; print('✓ audit_service')"
uv run python -c "from app.services.conflict_detector import ConflictDetector; print('✓ conflict_detector')"
uv run python -c "from app.services.rule_service import RuleService; print('✓ rule_service')"

echo "Starting server..."
uv run uvicorn app.main:app --reload