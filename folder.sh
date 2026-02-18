#!/bin/bash

# Create rules-engine structure
mkdir -p rules-engine/backend/app/{models,schemas,api/routes,services,engine,workers,utils}
mkdir -p rules-engine/backend/tests
mkdir -p rules-engine/frontend/{css,js}

# Backend files
touch rules-engine/backend/app/__init__.py
touch rules-engine/backend/app/main.py
touch rules-engine/backend/app/config.py
touch rules-engine/backend/app/database.py

touch rules-engine/backend/app/models/__init__.py
touch rules-engine/backend/app/models/rule.py
touch rules-engine/backend/app/models/user.py
touch rules-engine/backend/app/models/audit.py

touch rules-engine/backend/app/schemas/__init__.py
touch rules-engine/backend/app/schemas/rule.py
touch rules-engine/backend/app/schemas/user.py
touch rules-engine/backend/app/schemas/event.py

touch rules-engine/backend/app/api/__init__.py
touch rules-engine/backend/app/api/deps.py

touch rules-engine/backend/app/api/routes/__init__.py
touch rules-engine/backend/app/api/routes/rules.py
touch rules-engine/backend/app/api/routes/auth.py
touch rules-engine/backend/app/api/routes/events.py
touch rules-engine/backend/app/api/routes/metrics.py

touch rules-engine/backend/app/services/__init__.py
touch rules-engine/backend/app/services/rule_service.py
touch rules-engine/backend/app/services/auth_service.py
touch rules-engine/backend/app/services/audit_service.py
touch rules-engine/backend/app/services/conflict_detector.py

touch rules-engine/backend/app/engine/__init__.py
touch rules-engine/backend/app/engine/rete_engine.py
touch rules-engine/backend/app/engine/dsl_parser.py
touch rules-engine/backend/app/engine/dependency_graph.py
touch rules-engine/backend/app/engine/profiler.py

touch rules-engine/backend/app/workers/__init__.py
touch rules-engine/backend/app/workers/event_worker.py

touch rules-engine/backend/app/utils/__init__.py
touch rules-engine/backend/app/utils/redis_client.py
touch rules-engine/backend/app/utils/metrics.py

touch rules-engine/backend/tests/__init__.py
touch rules-engine/backend/tests/test_rule_service.py
touch rules-engine/backend/tests/test_dsl_parser.py
touch rules-engine/backend/tests/test_rete_engine.py
touch rules-engine/backend/tests/test_conflict_detector.py
touch rules-engine/backend/tests/test_dependency_graph.py
touch rules-engine/backend/tests/test_api.py

touch rules-engine/backend/requirements.txt
touch rules-engine/backend/Dockerfile
touch rules-engine/backend/pytest.ini

# Frontend files
touch rules-engine/frontend/index.html
touch rules-engine/frontend/login.html
touch rules-engine/frontend/css/style.css

touch rules-engine/frontend/js/app.js
touch rules-engine/frontend/js/auth.js
touch rules-engine/frontend/js/rule-builder.js
touch rules-engine/frontend/js/rule-list.js
touch rules-engine/frontend/js/rule-editor.js
touch rules-engine/frontend/js/test-sandbox.js
touch rules-engine/frontend/js/dependency-graph.js
touch rules-engine/frontend/js/metrics-viewer.js
touch rules-engine/frontend/js/version-diff.js

# Root files
touch rules-engine/docker-compose.yml
touch rules-engine/setup.sh
touch rules-engine/README.md

chmod +x rules-engine/setup.sh

echo "rules-engine structure created successfully!"
echo "Navigate to rules-engine/ directory and start copying the code files."