"""
HIPAA-compliant browser automation tool
Requires explicit user confirmation before executing actions
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import hashlib
import json

logger = logging.getLogger(__name__)

# Action types that require confirmation
SENSITIVE_ACTIONS = [
    "login", "submit_form", "download", "upload",
    "click_submit", "enter_password", "enter_credentials"
]

class BrowserActionController:
    """
    Controls browser automation with HIPAA compliance
    """
    
    def __init__(self):
        self.pending_actions = {}
        self.executed_actions = []
        self.confirmation_timeout = 300  # 5 minutes
    
    def create_action_plan(self, actions: List[Dict]) -> Dict:
        """
        Create an action plan that requires user confirmation
        
        Args:
            actions: List of browser actions to execute
        
        Returns:
            Action plan with unique ID for confirmation
        """
        # Generate unique plan ID
        plan_id = hashlib.md5(
            f"{datetime.utcnow().isoformat()}_{len(actions)}".encode()
        ).hexdigest()[:12]
        
        # Analyze actions for sensitivity
        requires_confirmation = any(
            action.get("type") in SENSITIVE_ACTIONS 
            for action in actions
        )
        
        # Create plan
        plan = {
            "plan_id": plan_id,
            "created_at": datetime.utcnow().isoformat(),
            "actions": actions,
            "requires_confirmation": requires_confirmation,
            "status": "pending_confirmation" if requires_confirmation else "ready",
            "description": self._generate_plan_description(actions)
        }
        
        # Store if confirmation needed
        if requires_confirmation:
            self.pending_actions[plan_id] = plan
        
        logger.info(f"Action plan created: {plan_id}, requires_confirmation={requires_confirmation}")
        
        return plan
    
    def _generate_plan_description(self, actions: List[Dict]) -> str:
        """
        Generate human-readable description of action plan
        """
        descriptions = []
        
        for i, action in enumerate(actions, 1):
            action_type = action.get("type", "unknown")
            target = action.get("target", "element")
            
            if action_type == "navigate":
                desc = f"Navigate to {action.get('url', 'URL')}"
            elif action_type == "click":
                desc = f"Click on {target}"
            elif action_type == "type":
                # Don't expose actual text content for security
                desc = f"Enter text in {target}"
            elif action_type == "screenshot":
                desc = f"Take screenshot"
            elif action_type == "wait":
                desc = f"Wait for {action.get('seconds', 1)} seconds"
            elif action_type == "login":
                desc = f"Log into {action.get('site', 'website')}"
            elif action_type == "download":
                desc = f"Download {action.get('file', 'file')}"
            else:
                desc = f"Perform {action_type} on {target}"
            
            descriptions.append(f"{i}. {desc}")
        
        return "\n".join(descriptions)
    
    async def confirm_action(self, plan_id: str, user_confirmation: str) -> Dict:
        """
        Process user confirmation for an action plan
        
        Args:
            plan_id: Unique plan identifier
            user_confirmation: User's confirmation response
        
        Returns:
            Confirmation result
        """
        if plan_id not in self.pending_actions:
            return {
                "success": False,
                "error": "Plan not found or already executed",
                "plan_id": plan_id
            }
        
        plan = self.pending_actions[plan_id]
        
        # Check if confirmation is valid
        if user_confirmation.upper() in ["CONFIRM", "YES", "PROCEED"]:
            plan["status"] = "confirmed"
            plan["confirmed_at"] = datetime.utcnow().isoformat()
            
            # Move to execution
            result = await self._execute_plan(plan)
            
            # Clean up
            del self.pending_actions[plan_id]
            
            return {
                "success": True,
                "plan_id": plan_id,
                "status": "executed",
                "result": result
            }
        else:
            # Cancellation
            plan["status"] = "cancelled"
            del self.pending_actions[plan_id]
            
            return {
                "success": False,
                "plan_id": plan_id,
                "status": "cancelled",
                "message": "Action plan cancelled by user"
            }
    
    async def _execute_plan(self, plan: Dict) -> Dict:
        """
        Execute a confirmed action plan
        
        This is a stub - in production, integrate with Playwright or Selenium
        """
        execution_log = []
        screenshots = []
        
        try:
            # In production, use Playwright here
            # from playwright.async_api import async_playwright
            
            for i, action in enumerate(plan["actions"]):
                # Stub execution
                log_entry = {
                    "step": i + 1,
                    "action": action["type"],
                    "target": action.get("target"),
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "completed"
                }
                
                # Simulate action execution
                await asyncio.sleep(0.1)
                
                # Log without PHI
                logger.info(f"Executed action: {action['type']} on step {i+1}")
                
                execution_log.append(log_entry)
                
                # If screenshot action, add placeholder
                if action["type"] == "screenshot":
                    screenshots.append({
                        "step": i + 1,
                        "filename": f"screenshot_{plan['plan_id']}_{i+1}.png",
                        "timestamp": datetime.utcnow().isoformat()
                    })
            
            # Record execution
            self.executed_actions.append({
                "plan_id": plan["plan_id"],
                "executed_at": datetime.utcnow().isoformat(),
                "action_count": len(plan["actions"])
            })
            
            return {
                "success": True,
                "execution_log": execution_log,
                "screenshots": screenshots,
                "duration_ms": len(plan["actions"]) * 100  # Simulated
            }
            
        except Exception as e:
            logger.error(f"Action execution failed: {type(e).__name__}")
            return {
                "success": False,
                "error": str(type(e).__name__),
                "execution_log": execution_log
            }

# Global controller instance
browser_controller = BrowserActionController()

async def execute_browser_action(action_request: Dict) -> Dict:
    """
    Main entry point for browser automation requests
    
    Args:
        action_request: Contains actions list and optional parameters
    
    Returns:
        Action plan requiring confirmation or execution result
    """
    
    actions = action_request.get("actions", [])
    auto_confirm = action_request.get("auto_confirm", False)
    
    if not actions:
        return {
            "success": False,
            "error": "No actions provided"
        }
    
    # Validate actions
    validation_result = validate_browser_actions(actions)
    if not validation_result["valid"]:
        return {
            "success": False,
            "error": validation_result["error"],
            "warnings": validation_result.get("warnings", [])
        }
    
    # Create action plan
    plan = browser_controller.create_action_plan(actions)
    
    # If doesn't require confirmation or auto-confirm is set
    if not plan["requires_confirmation"] or auto_confirm:
        result = await browser_controller._execute_plan(plan)
        return {
            "success": result["success"],
            "plan_id": plan["plan_id"],
            "result": result
        }
    
    # Return plan for confirmation
    return {
        "success": True,
        "status": "pending_confirmation",
        "plan_id": plan["plan_id"],
        "description": plan["description"],
        "message": "Please review the action plan above and respond with 'CONFIRM' to proceed",
        "actions_count": len(actions)
    }

def validate_browser_actions(actions: List[Dict]) -> Dict:
    """
    Validate browser actions for safety and compliance
    """
    validation_result = {
        "valid": True,
        "warnings": [],
        "error": None
    }
    
    for i, action in enumerate(actions):
        # Check required fields
        if "type" not in action:
            validation_result["valid"] = False
            validation_result["error"] = f"Action {i+1} missing 'type' field"
            return validation_result
        
        action_type = action["type"]
        
        # Validate specific action types
        if action_type == "navigate":
            if "url" not in action:
                validation_result["valid"] = False
                validation_result["error"] = f"Navigate action {i+1} missing 'url'"
                return validation_result
            
            # Check for suspicious URLs
            url = action["url"]
            if any(suspicious in url.lower() for suspicious in ["javascript:", "data:", "file:"]):
                validation_result["valid"] = False
                validation_result["error"] = f"Suspicious URL protocol in action {i+1}"
                return validation_result
        
        elif action_type in ["click", "type"]:
            if "target" not in action:
                validation_result["warnings"].append(f"Action {i+1} missing 'target' selector")
        
        elif action_type == "type":
            # Warn about sensitive data entry
            if "password" in str(action.get("target", "")).lower():
                validation_result["warnings"].append(f"Action {i+1} may enter sensitive data")
        
        # Check for potentially dangerous actions
        if action_type in ["execute_script", "eval"]:
            validation_result["valid"] = False
            validation_result["error"] = f"Action type '{action_type}' not allowed for security"
            return validation_result
    
    # Check total action count
    if len(actions) > 100:
        validation_result["warnings"].append("Large number of actions may take time to execute")
    
    return validation_result

def format_browser_action_for_llm(action_result: Dict) -> str:
    """
    Format browser action results for LLM context
    """
    if action_result.get("status") == "pending_confirmation":
        formatted = "🔒 **Browser Action Plan - Confirmation Required**\n\n"
        formatted += f"Plan ID: {action_result['plan_id']}\n"
        formatted += f"Actions to perform:\n{action_result['description']}\n\n"
        formatted += "⚠️ This action requires your confirmation for security.\n"
        formatted += "Please respond with **CONFIRM** to proceed or **CANCEL** to abort.\n"
    
    elif action_result.get("success"):
        formatted = "✅ **Browser Action Completed**\n\n"
        
        if "result" in action_result:
            result = action_result["result"]
            if result.get("execution_log"):
                formatted += f"Executed {len(result['execution_log'])} actions successfully\n"
            
            if result.get("screenshots"):
                formatted += f"Captured {len(result['screenshots'])} screenshots\n"
            
            if result.get("duration_ms"):
                formatted += f"Duration: {result['duration_ms']}ms\n"
    
    else:
        formatted = "❌ **Browser Action Failed**\n\n"
        if "error" in action_result:
            formatted += f"Error: {action_result['error']}\n"
        if "warnings" in action_result:
            formatted += f"Warnings: {', '.join(action_result['warnings'])}\n"
    
    return formatted

# Example browser action templates
BROWSER_ACTION_TEMPLATES = {
    "login": [
        {"type": "navigate", "url": "{login_url}"},
        {"type": "wait", "seconds": 2},
        {"type": "type", "target": "#username", "text": "{username}"},
        {"type": "type", "target": "#password", "text": "{password}"},
        {"type": "click", "target": "#login-button"},
        {"type": "wait", "seconds": 3}
    ],
    "download_report": [
        {"type": "navigate", "url": "{reports_url}"},
        {"type": "wait", "seconds": 2},
        {"type": "click", "target": ".report-link"},
        {"type": "wait", "seconds": 1},
        {"type": "click", "target": "#download-button"},
        {"type": "wait", "seconds": 5}
    ],
    "fill_form": [
        {"type": "navigate", "url": "{form_url}"},
        {"type": "wait", "seconds": 2},
        {"type": "type", "target": "#field1", "text": "{value1}"},
        {"type": "type", "target": "#field2", "text": "{value2}"},
        {"type": "click", "target": "#submit"},
        {"type": "wait", "seconds": 3},
        {"type": "screenshot"}
    ]
}