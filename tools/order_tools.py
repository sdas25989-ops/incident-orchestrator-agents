"""
Order Management API tool definition and handler.
"""

from clients.order_api import OrderAPIClient

TOOL_CANCEL_ORDER = {
    "name": "cancel_order",
    "description": (
        "Cancel a customer order via the Order Management API. "
        "Call only after extracting a valid order ID from the incident. "
        "Returns success/failure and a message from the Order API."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": (
                    "The order identifier extracted from the incident description. "
                    "Examples: 'ORD-12345', 'order #9876'. Strip any prefix and pass clean ID."
                )
            }
        },
        "required": ["order_id"]
    }
}


def handle_cancel_order(order_api: OrderAPIClient, tool_input: dict) -> dict:
    result = order_api.cancel_order(tool_input["order_id"])
    return {
        "success": result.success,
        "order_id": tool_input["order_id"],
        "message": result.message,
    }


ORDER_TOOL_DEFINITIONS = [TOOL_CANCEL_ORDER]

ORDER_TOOL_HANDLERS = {
    "cancel_order": handle_cancel_order,
}
