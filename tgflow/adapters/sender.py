"""Message delivery — sends the payload to the target.

Two transports are supported and share the same payload builder:

* ``bot``   — real inline keyboard (Telegram only allows bots to do that),
* ``admin`` — anonymous admin / channel identity, links embedded in the body.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from tgflow.core import MessageContext, utf16_len

log = logging.getLogger("tgflow.sender")

MEDIA_TMP_DIR = "/tmp/tgflow_media"
MAX_MEDIA_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25MB cap


class Sender:
    """Builds and delivers the outgoing message."""

    def __init__(self, *, media_tmp_dir: str = MEDIA_TMP_DIR) -> None:
        self.media_tmp_dir = media_tmp_dir
        try:
            os.makedirs(media_tmp_dir, exist_ok=True)
        except OSError:
            pass

    # ---- payload -------------------------------------------------------
    def build_payload(self, ctx: MessageContext, *, with_buttons: bool) -> dict[str, Any]:
        """Assemble kwargs for Telethon's send_message / send_file."""
        text = ctx.text or ""
        entities = list(ctx.entities or [])
        buttons = ctx.extras.get("buttons") or []

        if not with_buttons and buttons:
            text, entities = self.merge_buttons_into_text(text, entities, buttons)

        kwargs: dict[str, Any] = {}
        if entities:
            kwargs["formatting_entities"] = entities
        if with_buttons and buttons:
            kwargs["buttons"] = buttons
        return {"text": text, "kwargs": kwargs}

    def merge_buttons_into_text(
        self, text: str, entities: list[Any], buttons: list[list[tuple[str, str]]]
    ) -> tuple[str, list[Any]]:
        """Embed URL buttons as clickable TextUrl links in the body.

        Anonymous admins cannot attach reply_markup — Telegram drops it.
        """
        from tgflow.adapters.telegram import flatten_buttons

        pairs = flatten_buttons(buttons)
        if not pairs:
            return text, list(entities or [])

        base = text or ""
        existing_urls = {
            getattr(e, "url", None) for e in (entities or []) if getattr(e, "url", None)
        }
        to_add = [(label, url) for label, url in pairs if url not in base and url not in existing_urls]
        if not to_add:
            return base, list(entities or [])

        ents = list(entities or [])
        new_text = base
        for label, url in to_add:
            if new_text and not new_text.endswith("\n"):
                new_text += "\n"
            if new_text:
                new_text += "\n"
            offset = utf16_len(new_text)
            new_text += label
            from telethon.tl.types import MessageEntityTextUrl

            ents.append(MessageEntityTextUrl(offset=offset, length=utf16_len(label), url=url))
        return new_text, ents

    # ---- delivery ------------------------------------------------------
    async def send_via_bot(self, bot_client: Any, listen_client: Any, target: Any, ctx: MessageContext) -> None:
        """Send through a bot client — keeps the real inline keyboard."""
        from telethon import utils

        if not bot_client.is_connected():
            try:
                await bot_client.connect()
            except Exception as ce:
                log.warning("bot reconnect failed: %s", ce)

        try:
            target = await bot_client.get_entity(utils.get_peer_id(target))
        except Exception:
            uname = getattr(target, "username", None)
            target = await bot_client.get_entity(uname) if uname else await bot_client.get_entity(target)

        payload = self.build_payload(ctx, with_buttons=True)
        text = payload["text"]
        kwargs = payload["kwargs"]

        media = getattr(ctx.message, "media", None)
        file_size = getattr(getattr(ctx.message, "file", None), "size", 0) or 0
        if media and type(media).__name__ != "MessageMediaWebPage":
            if file_size > MAX_MEDIA_DOWNLOAD_BYTES:
                log.warning("media %.2fMB over cap, text only", file_size / (1024 * 1024))
            else:
                path = await self._download(listen_client, ctx.message)
                try:
                    kw = dict(kwargs)
                    kw["caption"] = text or None
                    await bot_client.send_file(target, path, **kw)
                    return
                finally:
                    self._cleanup(path)
        await bot_client.send_message(target, text or "\u200b", **kwargs)

    async def send_via_admin(self, client: Any, target: Any, ctx: MessageContext) -> None:
        """Send as anonymous admin / channel identity — links go into the body."""
        from telethon.tl.functions.messages import SaveDefaultSendAsRequest
        from telethon.tl.types import Channel

        payload = self.build_payload(ctx, with_buttons=False)
        text = payload["text"]
        kwargs = payload["kwargs"]

        if isinstance(target, Channel):
            if bool(target.megagroup):
                await self._ensure_anonymous_admin(client, target)
            elif bool(target.broadcast):
                try:
                    await client(SaveDefaultSendAsRequest(target, target))
                except Exception:
                    pass

        media = getattr(ctx.message, "media", None)
        file_size = getattr(getattr(ctx.message, "file", None), "size", 0) or 0
        if media and type(media).__name__ != "MessageMediaWebPage":
            if file_size > MAX_MEDIA_DOWNLOAD_BYTES:
                log.warning("media %.2fMB over cap, text only", file_size / (1024 * 1024))
            else:
                path = await self._download(client, ctx.message)
                try:
                    kw = dict(kwargs)
                    kw["caption"] = text or None
                    await client.send_file(target, path, **kw)
                    return
                finally:
                    self._cleanup(path)
        await client.send_message(target, text or "\u200b", **kwargs)

    async def _ensure_anonymous_admin(self, client: Any, target: Any) -> bool:
        """Grant the listening user anonymous-admin rights in the target group."""
        from telethon.tl.functions.channels import EditAdminRequest, GetParticipantRequest
        from telethon.tl.types import Channel, ChannelParticipantCreator, ChatAdminRights
        from telethon.tl.functions.messages import SaveDefaultSendAsRequest

        try:
            if not (isinstance(target, Channel) and bool(target.megagroup)):
                return False
            me = await client.get_me()
            part = (await client(GetParticipantRequest(target, me))).participant
            rights = getattr(part, "admin_rights", None)
            if rights is not None and getattr(rights, "anonymous", False):
                try:
                    await client(SaveDefaultSendAsRequest(target, target))
                except Exception:
                    pass
                return True
            new_rights = ChatAdminRights(
                change_info=True,
                post_messages=True,
                edit_messages=True,
                delete_messages=True,
                ban_users=True,
                invite_users=True,
                pin_messages=True,
                add_admins=bool(getattr(rights, "add_admins", False))
                if rights is not None
                else isinstance(part, ChannelParticipantCreator),
                anonymous=True,
                manage_call=True,
                other=True,
                manage_topics=True,
                post_stories=True,
                edit_stories=True,
                delete_stories=True,
            )
            await client(EditAdminRequest(target, me, new_rights, "anon"))
            try:
                await client(SaveDefaultSendAsRequest(target, target))
            except Exception:
                pass
            log.info("anonymous admin enabled: %s", getattr(target, "title", target.id))
            return True
        except Exception as e:
            log.warning("enable anonymous admin failed: %s", e)
            return False

    async def _download(self, client: Any, message: Any) -> str:
        name = f"msg_{getattr(message, 'id', 'x')}_{int(time.time() * 1000)}"
        path = os.path.join(self.media_tmp_dir, name)
        return await client.download_media(message, file=path)

    @staticmethod
    def _cleanup(path: Any) -> None:
        if isinstance(path, str) and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


class Throttle:
    """Smooth per-target rate limiter (leaky bucket)."""

    def __init__(self, min_gap: float = 1.5) -> None:
        self.min_gap = min_gap
        self._locks: dict[int, Any] = {}
        self._last: dict[int, float] = {}

    async def wait(self, target: Any) -> None:
        import asyncio

        tid = getattr(target, "id", None) or 0
        lock = self._locks.setdefault(tid, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            gap = now - self._last.get(tid, 0.0)
            if gap < self.min_gap:
                await asyncio.sleep(self.min_gap - gap)
            self._last[tid] = time.monotonic()
