"""Per-message execution context travelling through the plugin chain."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MessageContext:
    """Mutable state for one inbound message.

    Plugins receive this object and may read everything and write the parts
    they own. ``text`` / ``entities`` are the payload that will be delivered.
    """

    message: Any
    source: str = ""
    target: Any = None
    route: dict[str, Any] = field(default_factory=dict)
    account: dict[str, Any] = field(default_factory=dict)

    text: str = ""
    entities: list[Any] = field(default_factory=list)

    #: Set by a filter plugin to stop the pipeline.
    drop: bool = False
    drop_reason: str = ""

    delivered: bool = False
    error: str = ""

    #: Free-form scratch space shared between plugins.
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text:
            msg = self.message
            for attr in ("message", "text", "caption"):
                val = getattr(msg, attr, None)
                if isinstance(val, str) and val:
                    self.text = val
                    break
        if not self.entities:
            self.entities = list(getattr(self.message, "entities", None) or [])

    def drop_with(self, reason: str) -> None:
        """Veto this message with a human-readable reason."""
        self.drop = True
        self.drop_reason = reason

    def make_text_url(self, offset: int, length: int, url: str) -> Any:
        """Create a TextUrl entity.

        Provided by the runtime adapter (Telethon implementation); plugins
        should call this instead of importing a Telegram library directly.
        """
        factory = self.extras.get("make_text_url")
        if factory is None:
            raise RuntimeError("no entity factory available in ctx.extras")
        return factory(offset, length, url)
