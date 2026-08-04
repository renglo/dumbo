"""Dumbo extension — flat LangGraph smart-model agent harness for Renglo."""

__version__ = "1.0.0"
__all__ = ["get_handler", "list_handlers", "HANDLERS"]


def _get_dumbo_onboardings():
    from dumbo.handlers.dumbo_onboardings import DumboOnboardings

    return DumboOnboardings


HANDLERS = {
    "dumbo_onboardings": _get_dumbo_onboardings,
    "seed_demo_tools": lambda: __import__(
        "dumbo.handlers.seed_demo_tools", fromlist=["SeedDemoTools"]
    ).SeedDemoTools(),
}


def get_handler(handler_name: str):
    """Get an instantiated handler by name."""
    if handler_name not in HANDLERS:
        available = ", ".join(HANDLERS.keys())
        raise KeyError(
            f"Handler '{handler_name}' not found. Available handlers: {available}"
        )

    return HANDLERS[handler_name]()


def list_handlers():
    """List all available handler names."""
    return list(HANDLERS.keys())
