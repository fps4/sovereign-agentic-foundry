from __future__ import annotations

import asyncio
import logging
import os

import httpx
from aiogram import Bot, Dispatcher, Router
from pythonjsonlogger.jsonlogger import JsonFormatter
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

from storage import PostgresStorage


def _setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


log = _setup_logger("telegram-bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8000")
INVITE_CODE = os.getenv("INVITE_CODE", "")
DB_URL = os.getenv("DB_URL", "")

if not INVITE_CODE:
    log.warning("INVITE_CODE is not set — registration is open to anyone")

bot = Bot(token=BOT_TOKEN)
router = Router()


# ── FSM states ────────────────────────────────────────────────────────────────

class RegistrationStates(StatesGroup):
    waiting_invite = State()


class BuildStates(StatesGroup):
    waiting_description = State()


class FixStates(StatesGroup):
    waiting_app_selection = State()
    waiting_issue_description = State()


class DeleteStates(StatesGroup):
    waiting_app_selection = State()
    waiting_confirmation = State()


# ── Copy ──────────────────────────────────────────────────────────────────────

_HELP_REGISTERED = (
    "Here's what I can do for you:\n\n"
    "*Build an app*\n"
    "Just tell me what you need in plain language, or use /build for a guided flow.\n\n"
    "I can build:\n"
    "• *Forms* — capture and manage information\n"
    "• *Dashboards* — display data at a glance\n"
    "• *Workflows* — guide tasks through steps or approvals\n"
    "• *Connectors* — connect two services behind the scenes\n"
    "• *Assistants* — answer questions from your documents\n\n"
    "*Commands*\n"
    "/build — start building a new app\n"
    "/fix — report an issue in one of your apps\n"
    "/delete — permanently delete an app\n"
    "/apps — see your apps\n"
    "/help — show this message"
)

_INVITE_PROMPT = (
    "Hi! To get started, enter your invitation code.\n\n"
    "Don't have one? Contact the platform admin to get access."
)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _is_registered(telegram_id: int) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{ORCHESTRATOR_URL}/me", params={"telegram_id": telegram_id}
            )
            resp.raise_for_status()
            return resp.json().get("registered", False)
    except httpx.HTTPError:
        return False


async def _fetch_apps(telegram_id: int) -> list[dict] | None:
    """Return list of apps or None on error."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{ORCHESTRATOR_URL}/apps", params={"telegram_id": telegram_id}
            )
            if resp.status_code == 403:
                return []
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError:
        return None


async def _begin_registration(message: Message, state: FSMContext) -> None:
    await state.set_state(RegistrationStates.waiting_invite)
    await message.answer(_INVITE_PROMPT)


# ── Commands ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    registered = await _is_registered(message.from_user.id)
    if registered:
        await message.answer(
            f"Welcome back, {message.from_user.first_name}!\n\n{_HELP_REGISTERED}",
            parse_mode="Markdown",
        )
    else:
        await _begin_registration(message, state)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    registered = await _is_registered(message.from_user.id)
    if registered:
        await message.answer(_HELP_REGISTERED, parse_mode="Markdown")
    else:
        await message.answer("Send /register to create your account and get started.")


@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext) -> None:
    registered = await _is_registered(message.from_user.id)
    if registered:
        await message.answer(
            "You're already set up! Send /help to see what I can build for you."
        )
        return
    await _begin_registration(message, state)


@router.message(Command("apps"))
async def cmd_apps(message: Message) -> None:
    await bot.send_chat_action(message.chat.id, "typing")
    apps = await _fetch_apps(message.from_user.id)
    if apps is None:
        await message.answer("Something went wrong on our end. Please try again in a moment.")
        return
    if not apps:
        await message.answer(
            "You haven't built anything yet. Use /build to create your first app!"
        )
        return
    lines = ["*Your Apps*\n"]
    for app in apps:
        status = app["status"]
        issue_count = app.get("issue_count", 0)
        badge = f"[{status}"
        if issue_count:
            badge += f", {issue_count} issue{'s' if issue_count != 1 else ''}"
        badge += "]"
        url = app.get("url") or ""
        name_part = f"[{app['name']}]({url})" if url else app["name"]
        lines.append(f"• {name_part} {badge} — {app['description']}")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("build"))
async def cmd_build(message: Message, state: FSMContext) -> None:
    registered = await _is_registered(message.from_user.id)
    if not registered:
        await message.answer("Send /register to create your account and get started.")
        return
    await state.set_state(BuildStates.waiting_description)
    await message.answer(
        "What would you like to build? Describe it in plain language — "
        "for example: _a form to collect job applications_ or _a sales dashboard_.",
        parse_mode="Markdown",
    )


@router.message(Command("fix"))
async def cmd_fix(message: Message, state: FSMContext) -> None:
    registered = await _is_registered(message.from_user.id)
    if not registered:
        await message.answer("Send /register to create your account and get started.")
        return

    await bot.send_chat_action(message.chat.id, "typing")
    apps = await _fetch_apps(message.from_user.id)
    if apps is None:
        await message.answer("Something went wrong on our end. Please try again in a moment.")
        return
    if not apps:
        await message.answer(
            "You haven't built any apps yet. Use /build to create your first one!"
        )
        return

    await state.set_state(FixStates.waiting_app_selection)
    await state.update_data(apps=apps)

    lines = ["Which app has an issue? Reply with the number.\n"]
    for i, app in enumerate(apps, 1):
        lines.append(f"{i}. *{app['name']}* — {app['description']}")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("delete"))
async def cmd_delete(message: Message, state: FSMContext) -> None:
    registered = await _is_registered(message.from_user.id)
    if not registered:
        await message.answer("Send /register to create your account and get started.")
        return

    await bot.send_chat_action(message.chat.id, "typing")
    apps = await _fetch_apps(message.from_user.id)
    if apps is None:
        await message.answer("Something went wrong on our end. Please try again in a moment.")
        return
    if not apps:
        await message.answer(
            "You haven't built any apps yet. Use /build to create your first one!"
        )
        return

    await state.set_state(DeleteStates.waiting_app_selection)
    await state.update_data(apps=apps)

    lines = ["Which app do you want to delete? Reply with the number.\n"]
    for i, app in enumerate(apps, 1):
        lines.append(f"{i}. *{app['name']}* — {app['description']}")
    await message.answer("\n".join(lines), parse_mode="Markdown")


# ── Registration flow ─────────────────────────────────────────────────────────

@router.message(RegistrationStates.waiting_invite)
async def handle_invite_code(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    if INVITE_CODE and message.text.strip() != INVITE_CODE:
        await message.answer(
            "That invitation code doesn't look right. "
            "Try again or contact the platform admin to get access."
        )
        return

    username = message.from_user.username or message.from_user.first_name
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/register",
                json={
                    "telegram_id": message.from_user.id,
                    "telegram_username": username,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        log.error("Register request failed: %s", e)
        await message.answer("Something went wrong on our end. Please try again in a moment.")
        return

    if data["message"] == "already_registered":
        await state.clear()
        await message.answer(
            "You're already set up! Send /help to see what I can build for you."
        )
        return

    # Use the server-issued code directly — no need to show it to the user and ask them to re-enter it.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/verify",
                json={"telegram_id": message.from_user.id, "code": data["code"]},
            )
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPError as e:
        log.error("Verify request failed: %s", e)
        await state.clear()
        await message.answer("Something went wrong on our end. Please try again in a moment.")
        return

    await state.clear()
    if result["success"]:
        await message.answer(
            f"You're all set, {message.from_user.first_name}! Your personal space is ready.\n\n"
            + _HELP_REGISTERED,
            parse_mode="Markdown",
        )
    else:
        await message.answer("Something went wrong. Please send /register to start over.")


# ── Build flow ────────────────────────────────────────────────────────────────

@router.message(BuildStates.waiting_description)
async def handle_build_description(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    await state.clear()
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/chat",
                json={"user_id": str(message.from_user.id), "message": message.text},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        log.error("Orchestrator request failed: %s", e)
        await message.answer("Something went wrong on our end. Please try again in a moment.")
        return
    await message.answer(data["reply"], parse_mode="Markdown")


# ── Fix flow ──────────────────────────────────────────────────────────────────

@router.message(FixStates.waiting_app_selection)
async def handle_fix_app_selection(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    data = await state.get_data()
    apps = data.get("apps", [])

    text = message.text.strip()
    if not text.isdigit() or not (1 <= int(text) <= len(apps)):
        await message.answer(f"Please reply with a number between 1 and {len(apps)}.")
        return

    selected = apps[int(text) - 1]
    await state.update_data(selected_app=selected["name"])
    await state.set_state(FixStates.waiting_issue_description)
    await message.answer(
        f"Got it — *{selected['name']}*.\n\nDescribe what's going wrong. "
        "The more detail the better — include any error messages if you have them.",
        parse_mode="Markdown",
    )


@router.message(FixStates.waiting_issue_description)
async def handle_fix_description(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    data = await state.get_data()
    repo_name = data.get("selected_app", "")
    description = message.text.strip()
    title = description[:72] + ("…" if len(description) > 72 else "")

    await state.clear()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/issue",
                json={
                    "telegram_id": message.from_user.id,
                    "repo_name": repo_name,
                    "title": title,
                    "body": description,
                },
            )
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPError as e:
        log.error("Issue creation failed: %s", e)
        await message.answer("Something went wrong on our end. Please try again in a moment.")
        return

    await message.answer(
        f"Issue logged! It's been added to the queue and will be picked up shortly.\n\n"
        f"Track it here: {result['issue_url']}",
    )


# ── Delete flow ───────────────────────────────────────────────────────────────

@router.message(DeleteStates.waiting_app_selection)
async def handle_delete_app_selection(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    data = await state.get_data()
    apps = data.get("apps", [])

    text = message.text.strip()
    if not text.isdigit() or not (1 <= int(text) <= len(apps)):
        await message.answer(f"Please reply with a number between 1 and {len(apps)}.")
        return

    selected = apps[int(text) - 1]
    await state.update_data(selected_app=selected["name"])
    await state.set_state(DeleteStates.waiting_confirmation)
    await message.answer(
        f"Are you sure you want to permanently delete *{selected['name']}*? "
        "This cannot be undone.\n\nReply *yes* to confirm or anything else to cancel.",
        parse_mode="Markdown",
    )


@router.message(DeleteStates.waiting_confirmation)
async def handle_delete_confirmation(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    data = await state.get_data()
    repo_name = data.get("selected_app", "")

    if message.text.strip().lower() != "yes":
        await state.clear()
        await message.answer("Deletion cancelled.")
        return

    await state.clear()
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/delete-app",
                json={"telegram_id": message.from_user.id, "repo_name": repo_name},
            )
            if resp.status_code == 404:
                await message.answer(f"App *{repo_name}* not found.", parse_mode="Markdown")
                return
            resp.raise_for_status()
    except httpx.HTTPError as e:
        log.error("Delete app request failed: %s", e)
        await message.answer("Something went wrong on our end. Please try again in a moment.")
        return

    await message.answer(f"*{repo_name}* has been deleted.", parse_mode="Markdown")


# ── Main message handler ──────────────────────────────────────────────────────

@router.message()
async def handle_message(message: Message) -> None:
    if not message.text:
        return

    registered = await _is_registered(message.from_user.id)
    if not registered:
        await message.answer("Send /register to create your account and get started.")
        return

    await bot.send_chat_action(message.chat.id, "typing")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/chat",
                json={"user_id": str(message.from_user.id), "message": message.text},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        log.error("Orchestrator request failed: %s", e)
        await message.answer(
            "Something went wrong on our end. Please try again in a moment."
        )
        return

    await message.answer(data["reply"], parse_mode="Markdown")


async def main() -> None:
    log.info("Starting Telegram bot (polling)...", extra={"storage": "postgres" if DB_URL else "memory"})
    if DB_URL:
        log.info("Using PostgresStorage for FSM state persistence")
        storage = await PostgresStorage.create(DB_URL)
    else:
        log.warning("DB_URL not set — FSM state will not persist across restarts")
        storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
