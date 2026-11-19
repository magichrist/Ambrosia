"""Built-in action implementations.

Built-in actions are trusted in-process implementations registered against the
action registry. They are never executed as a side effect of registration or
discovery.
"""

from ambrosia.actions.builtins import CORE_ECHO_ACTION, EchoHandler, register_builtins

__all__ = ["CORE_ECHO_ACTION", "EchoHandler", "register_builtins"]
