# CSV Decision Tables - Two Styles

FluxRules supports **TWO styles of CSV** for loading rules:

## Style 1: Simple (single-condition rules)

**Columns:** `id`, `name`, `priority`, `fact`, `operator`, `value`, `action`, `enabled`

Each row = one condition. Same ID on multiple rows = AND group.

**Example:**
```
id,name,priority,fact,operator,value,action,enabled
1,high_value,10,amount,>,1000,flag,true
2,low_age,20,age,<,25,require,true
```

## Style 2: DSL (any complexity - single OR multi-condition)

**Columns:** `id`, `name`, `priority`, `condition_dsl`, `action`, `enabled`

The `condition_dsl` column contains a JSON condition object (properly escaped for CSV).

**Supports:**
- Single conditions
- AND groups
- OR groups
- Deeply nested conditions

**Example:**
```
id,name,priority,condition_dsl,action,enabled
1,high_value,10,"{""type"":""condition"",""field"":""amount"",""op"":"">"",""value"":1000}",flag,true
2,young_and_rich,20,"{""type"":""group"",""op"":""AND"",""children"":[{""type"":""condition"",""field"":""age"",""op"":""<"",""value"":25},{""type"":""condition"",""field"":""amount"",""op"":"">"",""value"":500}]}",escalate,true
```

## CSV Escaping for condition_dsl

Since `condition_dsl` is JSON in a CSV cell, escaping requires special handling.

### Option A: Double Quotes (most readable)

```python
condition_dsl = {"type":"condition","field":"amount","op":">","value":1000}
# In CSV: "{""type"":""condition"",""field"":""amount"",""op"":"">"",""value"":1000}"
```

### Option B: Single Quotes (for testing)

```python
condition_dsl = '{"type":"condition","field":"amount","op":">","value":1000}'
# CSV parser strips outer quotes
```

## Tool: Generate Valid DSL JSON

Use `jq` to format and escape:

```bash
jq -c '{type:"group",op:"AND",children:[...]}' | sed 's/"/\\"/g'
```

Or use Python:

```python
import json
import csv
from io import StringIO

condition = {
    "type": "group",
    "op": "AND",
    "children": [
        {"type": "condition", "field": "age", "op": "<", "value": 25},
        {"type": "condition", "field": "amount", "op": ">", "value": 500},
    ]
}

# Properly escape for CSV
csv_buffer = StringIO()
writer = csv.writer(csv_buffer)
writer.writerow([
    1,  # id
    "multi",  # name
    10,  # priority
    json.dumps(condition),  # condition_dsl (CSV writer handles escaping)
    "act",  # action
    True  # enabled
])
print(csv_buffer.getvalue())
```
