import asyncio
import logging
import os
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from styles import generate_styles, page_text, PAGE_SIZE, MAX_TEXT_LENGTH, MAX_PAGES

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
try:
    OWNER_ID = int(os.getenv("OWNER_ID", "8062657182"))
except ValueError as exc:
    raise RuntimeError("OWNER_ID باید عددي Telegram ID وي.") from exc
DB_PATH = os.getenv("DB_PATH", "font_style_bot.sqlite3").strip() or "font_style_bot.sqlite3"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fonts-tgbot")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم شوی نه دی. د JustRunMy Environment Variables کې BOT_TOKEN اضافه کړئ.")

dp = Dispatcher()
style_cache = {}

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def is_admin(user_id: int) -> bool:
    return is_owner(user_id) or db.is_admin(DB_PATH, user_id)

def esc(value) -> str:
    import html
    return html.escape(str(value or ""), quote=False)

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✨ فونټونه جوړول")],
            [KeyboardButton(text="📖 د بوټ لارښود")]
        ],
        resize_keyboard=True
    )

def admin_keyboard(user_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 د چینلونو لېست", callback_data="adm:channels")
    kb.button(text="➕ چینل اضافه کول", callback_data="adm:addch")
    kb.button(text="✏️ د چینل معلومات بدلول", callback_data="adm:editch")
    kb.button(text="➖ چینل حذف کول", callback_data="adm:delch")
    kb.button(text="👮 د اډمینونو لېست", callback_data="adm:admins")
    if is_owner(user_id):
        kb.button(text="➕ اډمین اضافه کول", callback_data="adm:addadmin")
        kb.button(text="➖ اډمین حذف کول", callback_data="adm:deladmin")
    kb.button(text="📊 احصایې", callback_data="adm:stats")
    kb.button(text="🏠 اصلي مېنو", callback_data="adm:home")
    kb.adjust(1)
    return kb.as_markup()

def join_keyboard(channels):
    kb = InlineKeyboardBuilder()
    for channel in channels:
        kb.button(text=f"📢 {channel['title']}", url=channel["invite_url"])
    kb.button(text="✅ ګډون مې کړی — تایید", callback_data="join:verify")
    kb.adjust(1)
    return kb.as_markup()

async def check_membership(bot: Bot, user_id: int):
    missing, errors = [], []
    for channel in db.get_channels(DB_PATH):
        try:
            member = await bot.get_chat_member(channel["channel_id"], user_id)
            if member.status not in ("member", "administrator", "creator"):
                missing.append(channel)
        except TelegramAPIError as exc:
            log.warning("getChatMember failed for configured channel; error_type=%s", type(exc).__name__)
            errors.append(channel)
        except Exception as exc:
            log.warning("Unexpected membership check error; error_type=%s", type(exc).__name__)
            errors.append(channel)
    return not missing and not errors, missing, errors

async def send_join_gate(message: Message, bot: Bot, missing=None, errors=None):
    missing = missing if missing is not None else db.get_channels(DB_PATH)
    errors = errors or []
    if errors:
        await message.answer(
            "⚠️ د ټیلیګرام له API سره د ګډون د تایید ستونزه ده. لاسرسی نه دی ورکړل شوی. "
            "وروسته بیا هڅه وکړئ او ډاډ ترلاسه کړئ چې بوټ په اړوندو چینلونو کې Administrator دی."
        )
    channels = list(missing) + [c for c in errors if c not in missing]
    if channels:
        await message.answer(
            "⛔ د بوټ د کارولو لپاره په ټولو اړینو چینلونو کې ګډون وکړئ:\n"
            "۱. د هر چینل تڼۍ پرانیزئ او Join شئ.\n"
            "۲. بېرته راشئ او «ګډون مې کړی — تایید» کېکاږئ.",
            reply_markup=join_keyboard(channels)
        )
    elif not errors:
        await message.answer("ښه راغلاست! له مېنو څخه یو انتخاب وکړئ.", reply_markup=main_keyboard())

async def require_membership(message: Message, bot: Bot) -> bool:
    ok, missing, errors = await check_membership(bot, message.from_user.id)
    if ok:
        return True
    await send_join_gate(message, bot, missing, errors)
    return False

def state_prompt(action):
    return {
        "addch": ("add_channel", "د چینل معلومات داسې راولېږئ:\n<code>@channelusername | نوم | https://t.me/channelusername</code>"),
        "editch": ("edit_channel", "د چینل معلومات داسې راولېږئ:\n<code>اوسنی_ID | نوی_ID | نوی نوم | نوی لینک</code>"),
        "delch": ("delete_channel", "د حذف لپاره د چینل ID یا username راولېږئ."),
        "addadmin": ("add_admin", "د نوي اډمین عددي Telegram ID راولېږئ."),
        "deladmin": ("delete_admin", "د حذف کېدونکي اډمین عددي Telegram ID راولېږئ.")
    }.get(action)

@dp.message(CommandStart())
async def start(message: Message, bot: Bot):
    db.touch_user(DB_PATH, message.from_user.id)
    await require_membership(message, bot)

@dp.message(Command("admin"))
async def admin_command(message: Message, bot: Bot):
    uid = message.from_user.id
    if not is_admin(uid):
        await message.answer("⛔ د اډمین پینل ته د لاسرسي اجازه نه لرئ.")
        return
    if not await require_membership(message, bot):
        return
    await message.answer("🛠 <b>د اډمین پینل</b>\nټول اداري بدلونونه د تایید وروسته عملي کېږي.",
                         reply_markup=admin_keyboard(uid))

@dp.message(Command("cancel"))
async def cancel_command(message: Message, bot: Bot):
    if not await require_membership(message, bot):
        return
    db.clear_state(DB_PATH, message.from_user.id)
    await message.answer("عملیات لغوه شول.", reply_markup=admin_keyboard(message.from_user.id) if is_admin(message.from_user.id) else main_keyboard())

@dp.callback_query(F.data.startswith("adm:"))
async def admin_callback(call: CallbackQuery):
    uid = call.from_user.id
    if not is_admin(uid):
        await call.answer("⛔ اجازه نه لرئ.", show_alert=True)
        return
    action = call.data.split(":", 1)[1]
    if action in ("addadmin", "deladmin") and not is_owner(uid):
        await call.answer("یوازې اصلي مالک اډمینونه اداره کولای شي.", show_alert=True)
        return
    ok, missing, errors = await check_membership(call.bot, uid)
    if not ok:
        await call.answer("لومړی ګډون تایید کړئ.", show_alert=True)
        await send_join_gate(call.message, call.bot, missing, errors)
        return
    await call.answer()
    if action == "home":
        await call.message.answer("🏠 اصلي مېنو", reply_markup=main_keyboard())
    elif action == "channels":
        channels = db.get_channels(DB_PATH)
        if channels:
            body = "📋 <b>ثبت شوي چینلونه</b>\n\n" + "\n\n".join(
                f"{i}. {esc(c['title'])}\nID: <code>{esc(c['channel_id'])}</code>\nلینک: {esc(c['invite_url'])}"
                for i, c in enumerate(channels, 1))
        else:
            body = "اوس مهال هېڅ چینل نه دی ثبت شوی."
        await call.message.answer(body, reply_markup=admin_keyboard(uid))
    elif action == "admins":
        ids = db.get_admin_ids(DB_PATH)
        body = "👮 <b>اډمینونه</b>\nاصلي مالک: <code>{}</code>".format(OWNER_ID)
        body += "\n" + ("\n".join(f"• <code>{i}</code>" for i in ids) if ids else "اضافي اډمین نشته.")
        await call.message.answer(body, reply_markup=admin_keyboard(uid))
    elif action == "stats":
        stats = db.get_stats(DB_PATH)
        await call.message.answer(
            f"📊 <b>احصایې</b>\nکاروونکي: {stats['users']}\nد متن غوښتنې: {stats['requests']}\n"
            f"چینلونه: {stats['channels']}\nاضافي اډمینونه: {stats['admins']}",
            reply_markup=admin_keyboard(uid))
    else:
        prompt = state_prompt(action)
        if not prompt:
            await call.message.answer("❌ نامعتبر انتخاب.", reply_markup=admin_keyboard(uid))
            return
        db.set_state(DB_PATH, uid, prompt[0])
        await call.message.answer(prompt[1] + "\n\nد لغوه کولو لپاره /cancel واستوئ.")

@dp.callback_query(F.data.startswith("pending:"))
async def pending_callback(call: CallbackQuery):
    uid = call.from_user.id
    if not is_admin(uid):
        await call.answer("⛔ اجازه نه لرئ.", show_alert=True)
        return
    ok, missing, errors = await check_membership(call.bot, uid)
    if not ok:
        await call.answer("لومړی ګډون تایید کړئ.", show_alert=True)
        await send_join_gate(call.message, call.bot, missing, errors)
        return
    try:
        _, choice, pending_id = call.data.split(":", 2)
        pending_id = int(pending_id)
    except (ValueError, TypeError):
        await call.answer("❌ نامعتبره غوښتنه.", show_alert=True)
        return
    item = db.get_pending(DB_PATH, pending_id)
    if not item or item["user_id"] != uid:
        await call.answer("❌ دا تایید نور معتبر نه دی.", show_alert=True)
        return
    action, payload = item["action"], item["payload"]
    if action in ("add_admin", "delete_admin") and not is_owner(uid):
        await call.answer("یوازې اصلي مالک اډمینونه اداره کولای شي.", show_alert=True)
        return
    if choice == "no":
        db.delete_pending(DB_PATH, pending_id)
        await call.answer("لغوه شو.")
        await call.message.edit_text("❌ عملیات لغوه شول.")
        return
    try:
        db.apply_pending(DB_PATH, pending_id, uid, OWNER_ID)
    except (ValueError, sqlite3.Error) as exc:
        log.warning("Admin operation failed; error_type=%s", type(exc).__name__)
        await call.answer("❌ عملیات ترسره نه شول. معلومات او واکونه وګورئ.", show_alert=True)
        return
    await call.answer("تایید او عملي شو.")
    await call.message.edit_text("✅ عملیات په بریالیتوب ترسره شو.")
    await call.message.answer("🛠 د اډمین پینل", reply_markup=admin_keyboard(uid))

@dp.callback_query(F.data == "join:verify")
async def join_verify(call: CallbackQuery, bot: Bot):
    ok, missing, errors = await check_membership(bot, call.from_user.id)
    if ok:
        await call.answer("ګډون تایید شو.")
        await call.message.answer("✅ ګډون تایید شو. اوس خدمت کارولی شئ.", reply_markup=main_keyboard())
    else:
        await call.answer("ګډون بشپړ نه دی یا تایید کې ستونزه ده.", show_alert=True)
        await send_join_gate(call.message, bot, missing, errors)

@dp.callback_query(F.data.startswith("styles:"))
async def styles_callback(call: CallbackQuery, bot: Bot):
    ok, missing, errors = await check_membership(bot, call.from_user.id)
    if not ok:
        await call.answer("د خدمت لپاره ګډون اړین دی.", show_alert=True)
        await send_join_gate(call.message, bot, missing, errors)
        return
    cached = style_cache.get(call.from_user.id)
    if not cached:
        await call.answer("مهرباني وکړئ متن بیا راولېږئ.", show_alert=True)
        return
    try:
        page = int(call.data.split(":", 1)[1])
    except ValueError:
        await call.answer("❌ د پاڼې شمېره ناسمه ده.", show_alert=True)
        return
    original, styles = cached
    body, total_pages = page_text(original, styles, page)
    page = max(0, min(page, total_pages - 1))
    kb = InlineKeyboardBuilder()
    if page > 0:
        kb.button(text="⬅️ مخکینۍ پاڼه", callback_data=f"styles:{page-1}")
    if page < total_pages - 1:
        kb.button(text="راتلونکې پاڼه ➡️", callback_data=f"styles:{page+1}")
    kb.adjust(2)
    try:
        await call.message.edit_text(body, reply_markup=kb.as_markup() if page > 0 or page < total_pages-1 else None)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            log.warning("Could not edit styles page: %s", type(exc).__name__)
    await call.answer()

@dp.message(F.text)
async def text_handler(message: Message, bot: Bot):
    uid = message.from_user.id
    text = (message.text or "").strip()
    db.touch_user(DB_PATH, uid)

    if not await require_membership(message, bot):
        return
    state = db.get_state(DB_PATH, uid) if is_admin(uid) else None
    if state and not text.startswith("/"):
        action = state["action"]
        if action in ("add_admin", "delete_admin") and not is_owner(uid):
            db.clear_state(DB_PATH, uid)
            await message.answer("⛔ یوازې اصلي مالک اډمینونه اداره کولای شي.")
            return
        try:
            pending_action, payload = db.parse_admin_input(action, text, OWNER_ID)
        except ValueError as exc:
            await message.answer(f"❌ {esc(str(exc))}")
            return
        pending_id = db.create_pending(DB_PATH, uid, pending_action, payload)
        db.clear_state(DB_PATH, uid)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ تایید او عملي کول", callback_data=f"pending:yes:{pending_id}"),
            InlineKeyboardButton(text="❌ لغوه", callback_data=f"pending:no:{pending_id}")
        ]])
        await message.answer("⚠️ د عملیاتو معلومات:\n" + esc(db.describe_pending(pending_action, payload)) +
                             "\n\nایا دا عملیات تاییدوئ؟", reply_markup=kb)
        return

    if not await require_membership(message, bot):
        return
    if text == "📖 د بوټ لارښود":
        await message.answer(
            "📖 <b>د بوټ لارښود</b>\n\n۱. «✨ فونټونه جوړول» کېکاږئ.\n۲. خپل نوم یا لنډ متن راولېږئ.\n"
            "۳. د پاڼو تڼۍ وکاروئ.\n۴. پر سټایل اوږد فشار وکړئ او Copy وټاکئ.\n\n"
            "یادونه: عادي Telegram بوټ د کاروونکي کلیپ‌بورډ په مستقیم ډول نه شي بدلولای. "
            "د پښتو، دري او عربي اصلي توري ساتل کېږي؛ د انګلیسي لپاره Unicode سټایلونه کارول کېږي.",
            reply_markup=main_keyboard())
        return
    if text == "✨ فونټونه جوړول":
        await message.answer("✍️ خپل نوم یا لنډ متن راولېږئ (تر ۸۰ تورو پورې).")
        return
    if text.startswith("/"):
        return
    if not text:
        await message.answer("❌ تش متن مه لېږئ.")
        return
    if len(text) > MAX_TEXT_LENGTH:
        await message.answer(f"⚠️ متن ډېر اوږد دی. تر {MAX_TEXT_LENGTH} تورو پورې متن راولېږئ.")
        return
    styles = generate_styles(text)
    if not styles:
        await message.answer("❌ د دې متن لپاره سټایلونه جوړ نه شول.")
        return
    db.increment_requests(DB_PATH, uid)
    style_cache[uid] = (text, styles)
    body, total_pages = page_text(text, styles, 0)
    kb = InlineKeyboardBuilder()
    if total_pages > 1:
        kb.button(text="راتلونکې پاڼه ➡️", callback_data="styles:1")
    await message.answer(body, reply_markup=kb.as_markup() if total_pages > 1 else None)

async def main():
    db.init_db(DB_PATH)
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    log.info("Bot started as @%s", me.username)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped.")
