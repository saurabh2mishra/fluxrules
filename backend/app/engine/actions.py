"""
Action Functions Registry

This module defines all available action functions that can be used in rules.
When a rule's conditions are met, the specified action function is executed.

To add a new action:
1. Define the function with @register_action decorator
2. The function receives (event, context) parameters
3. Document the function for UI display
"""

from typing import Dict, Any, Callable, List
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Registry to store all available actions
_ACTION_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_action(name: str, description: str, category: str = "general"):
    """Decorator to register an action function"""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        _ACTION_REGISTRY[name] = {
            "name": name,
            "function": wrapper,
            "description": description,
            "category": category,
            "parameters": getattr(func, '_parameters', [])
        }
        return wrapper
    return decorator


def get_available_actions() -> List[Dict[str, Any]]:
    """Get list of all available actions for UI display"""
    return [
        {
            "name": info["name"],
            "description": info["description"],
            "category": info["category"],
            "parameters": info["parameters"]
        }
        for name, info in _ACTION_REGISTRY.items()
    ]


def execute_action(action_name: str, event: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Execute a registered action"""
    if action_name not in _ACTION_REGISTRY:
        return {
            "success": False,
            "error": f"Unknown action: {action_name}",
            "available_actions": list(_ACTION_REGISTRY.keys())
        }
    
    try:
        result = _ACTION_REGISTRY[action_name]["function"](event, context or {})
        return {
            "success": True,
            "action": action_name,
            "result": result
        }
    except Exception as e:
        logger.error(f"Error executing action {action_name}: {e}")
        return {
            "success": False,
            "action": action_name,
            "error": str(e)
        }


# ============================================================================
# ALERT ACTIONS
# ============================================================================

@register_action(
    name="send_alert",
    description="Send an alert notification to configured channels (email, Slack, etc.)",
    category="alerts"
)
def send_alert(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Send an alert based on the event"""
    alert_type = context.get("alert_type", "default")
    message = context.get("message", f"Alert triggered for event: {event}")
    
    # TODO: Implement actual alert sending (email, Slack, webhook, etc.)
    logger.info(f"ALERT [{alert_type}]: {message}")
    
    return {
        "alert_sent": True,
        "alert_type": alert_type,
        "message": message
    }


@register_action(
    name="send_email",
    description="Send an email notification to specified recipients",
    category="alerts"
)
def send_email(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Send email notification"""
    recipients = context.get("recipients", [])
    subject = context.get("subject", "Rule Engine Alert")
    body = context.get("body", f"Event triggered: {event}")
    
    # TODO: Implement actual email sending
    logger.info(f"EMAIL to {recipients}: {subject}")
    
    return {
        "email_sent": True,
        "recipients": recipients,
        "subject": subject
    }


@register_action(
    name="send_slack",
    description="Send a message to a Slack channel",
    category="alerts"
)
def send_slack(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Send Slack notification"""
    channel = context.get("channel", "#alerts")
    message = context.get("message", f"Rule triggered: {event}")
    
    # TODO: Implement actual Slack integration
    logger.info(f"SLACK [{channel}]: {message}")
    
    return {
        "slack_sent": True,
        "channel": channel,
        "message": message
    }


# ============================================================================
# TRANSACTION ACTIONS
# ============================================================================

@register_action(
    name="block_transaction",
    description="Block/reject the current transaction",
    category="transactions"
)
def block_transaction(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Block a transaction"""
    reason = context.get("reason", "Blocked by rule engine")
    transaction_id = event.get("transaction_id", event.get("id", "unknown"))
    
    # TODO: Implement actual transaction blocking
    logger.warning(f"BLOCKED transaction {transaction_id}: {reason}")
    
    return {
        "blocked": True,
        "transaction_id": transaction_id,
        "reason": reason
    }


@register_action(
    name="flag_for_review",
    description="Flag the transaction/event for manual review",
    category="transactions"
)
def flag_for_review(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Flag for manual review"""
    priority = context.get("priority", "medium")
    notes = context.get("notes", "Flagged by rule engine")
    
    # TODO: Implement actual flagging (add to review queue, database, etc.)
    logger.info(f"FLAGGED for review [{priority}]: {notes}")
    
    return {
        "flagged": True,
        "priority": priority,
        "notes": notes
    }


@register_action(
    name="approve_transaction",
    description="Approve the transaction to proceed",
    category="transactions"
)
def approve_transaction(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Approve a transaction"""
    transaction_id = event.get("transaction_id", event.get("id", "unknown"))
    
    logger.info(f"APPROVED transaction {transaction_id}")
    
    return {
        "approved": True,
        "transaction_id": transaction_id
    }


# ============================================================================
# LOGGING ACTIONS
# ============================================================================

@register_action(
    name="log_event",
    description="Log the event with specified level and message",
    category="logging"
)
def log_event(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Log an event"""
    level = context.get("level", "info")
    message = context.get("message", f"Event logged: {event}")
    
    log_func = getattr(logger, level, logger.info)
    log_func(f"EVENT LOG: {message}")
    
    return {
        "logged": True,
        "level": level,
        "message": message
    }


@register_action(
    name="audit_log",
    description="Create an audit log entry for compliance tracking",
    category="logging"
)
def audit_log(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Create audit log entry"""
    action_type = context.get("action_type", "rule_triggered")
    details = context.get("details", str(event))
    
    # TODO: Implement actual audit logging (to database, file, etc.)
    logger.info(f"AUDIT [{action_type}]: {details}")
    
    return {
        "audit_logged": True,
        "action_type": action_type
    }


# ============================================================================
# DATA ACTIONS
# ============================================================================

@register_action(
    name="update_field",
    description="Update a field value in the event/record",
    category="data"
)
def update_field(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Update a field in the event"""
    field = context.get("field")
    value = context.get("value")
    
    if field:
        event[field] = value
        logger.info(f"UPDATED field {field} = {value}")
    
    return {
        "updated": True,
        "field": field,
        "new_value": value
    }


@register_action(
    name="enrich_data",
    description="Enrich event data with additional information from external sources",
    category="data"
)
def enrich_data(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Enrich event with additional data"""
    source = context.get("source", "internal")
    fields = context.get("fields", [])
    
    # TODO: Implement actual data enrichment (API calls, database lookups, etc.)
    logger.info(f"ENRICHING from {source}: {fields}")
    
    return {
        "enriched": True,
        "source": source,
        "fields": fields
    }


# ============================================================================
# WEBHOOK ACTIONS
# ============================================================================

@register_action(
    name="call_webhook",
    description="Call an external webhook/API endpoint",
    category="integrations"
)
def call_webhook(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Call external webhook"""
    url = context.get("url")
    method = context.get("method", "POST")
    
    # TODO: Implement actual webhook call using httpx or requests
    logger.info(f"WEBHOOK {method} {url}")
    
    return {
        "webhook_called": True,
        "url": url,
        "method": method
    }


@register_action(
    name="trigger_workflow",
    description="Trigger an external workflow or process",
    category="integrations"
)
def trigger_workflow(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Trigger external workflow"""
    workflow_id = context.get("workflow_id")
    parameters = context.get("parameters", {})
    
    # TODO: Implement workflow triggering
    logger.info(f"WORKFLOW triggered: {workflow_id}")
    
    return {
        "workflow_triggered": True,
        "workflow_id": workflow_id,
        "parameters": parameters
    }


# ============================================================================
# COMPOSITE ACTIONS
# ============================================================================

@register_action(
    name="no_action",
    description="Do nothing (useful for testing or placeholder rules)",
    category="utility"
)
def no_action(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """No operation - placeholder action"""
    return {"action": "none"}


@register_action(
    name="print_debug",
    description="Print debug information (for testing)",
    category="utility"
)
def print_debug(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Print debug info"""
    message = context.get("message", str(event))
    print(f"DEBUG: {message}")
    logger.debug(f"DEBUG: {message}")
    
    return {"debug": True, "message": message}
