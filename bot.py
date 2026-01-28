from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import os
import json
import uuid

# ================= CONFIG =================
TOKEN = os.getenv("BOT_TOKEN")

GROUP_ID = -1003733753242          # ОСНОВНАЯ ГРУППА
REVIEW_GROUP_ID = -1003838204103   # ГРУППА ПРОВЕРКИ
MENTIONS = "@anonim228m @Quintide"

DATA_FILE = "users.json"
PENDING_FILE = "pending.json"
SCREEN_DIR = "screens"

os.makedirs(SCREEN_DIR, exist_ok=True)

# ================= USERS =================
def load_users():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for u in data.values():
            u.setdefault("contracts", 0)
            u.setdefault("families", 0)
        return data
    return {}

def save_users():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

users = load_users()

# ================= PENDING =================
def load_pending():
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_pending(data):
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

pending = load_pending()

# ================= MENU =================
def menu():
    return ReplyKeyboardMarkup(
        [
            ["📊 Общая статистика"],
            ["➕ Добавить контракт"],
            ["👨‍👩‍👧 Добавить семью"],
            ["📈 UMO статистика"]
        ],
        resize_keyboard=True
    )

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("👋 Введите ваш ник для авторизации:")

# ================= AUTH =================
async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("nick"):
        return

    nick = update.message.text.strip()
    if nick not in users:
        await update.message.reply_text("❌ Ник не найден.")
        return

    context.user_data.update({
        "nick": nick,
        "state": None,
        "screens": [],
        "reject_id": None
    })

    await update.message.reply_text(
        f"✅ Добро пожаловать, {nick}\n"
        f"Должность: {users[nick]['role']}",
        reply_markup=menu()
    )

# ================= MENU HANDLER =================
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📊 Общая статистика":
        msg = "📊 Общая статистика:\n\n"
        for u, d in users.items():
            msg += (
                f"👤 {u} ({d['role']})\n"
                f"• Контракты: {d['contracts']}\n"
                f"• Семьи: {d['families']}\n\n"
            )
        await update.message.reply_text(msg)

    elif text == "➕ Добавить контракт":
        context.user_data["state"] = "contract"
        context.user_data["screens"] = []
        await update.message.reply_text("📸 Отправьте 2 скриншота.")

    elif text == "👨‍👩‍👧 Добавить семью":
        context.user_data["state"] = "family"
        context.user_data["screens"] = []
        await update.message.reply_text("📸 Отправьте 2 скриншота.")

    elif text == "📈 UMO статистика":
        await update.message.reply_text("📈 UMO статистика\n\nВ разработке 🚧")

# ================= PHOTOS =================
async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")
    nick = context.user_data.get("nick")
    if not state or not nick:
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()
    path = f"{SCREEN_DIR}/{uuid.uuid4()}.jpg"
    await file.download_to_drive(path)
    context.user_data["screens"].append(path)

    if len(context.user_data["screens"]) < 2:
        return

    caption = (
        f"📥 {'Контракт' if state == 'contract' else 'Семья'}\n"
        f"👤 {nick}\n"
        f"👔 {users[nick]['role']}"
    )

    # ---- СОХРАНЯЕМ ЗАЯВКУ ----
    req_id = str(uuid.uuid4())
    pending[req_id] = {
        "nick": nick,
        "chat_id": update.effective_chat.id,
        "type": state,
        "screens": context.user_data["screens"]
    }
    save_pending(pending)

    # ---- ОТПРАВКА ТОЛЬКО В ГРУППУ ПРОВЕРКИ ----
    media_review = [
        InputMediaPhoto(
            open(context.user_data["screens"][0], "rb"),
            caption=caption + f"\n\n👀 Заявка на проверке\n{MENTIONS}"
        ),
        InputMediaPhoto(open(context.user_data["screens"][1], "rb"))
    ]

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Принять", callback_data=f"approve:{req_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{req_id}")
        ]
    ])

    await context.bot.send_media_group(REVIEW_GROUP_ID, media_review)
    await context.bot.send_message(REVIEW_GROUP_ID, "Выберите действие:", reply_markup=keyboard)

    context.user_data["state"] = None
    context.user_data["screens"] = []

    await update.message.reply_text("✅ Заявка отправлена на проверку руководству.")

# ================= CALLBACKS =================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, req_id = query.data.split(":")

    if req_id not in pending:
        await query.message.reply_text("⚠️ Заявка уже обработана.")
        return

    data = pending[req_id]
    nick = data["nick"]
    req_type = data["type"]

    if action == "approve":
        # ---- ОБНОВЛЯЕМ СТАТИСТИКУ ----
        if req_type == "contract":
            users[nick]["contracts"] += 1
        elif req_type == "family":
            users[nick]["families"] += 1

        save_users()

        # ---- ПУБЛИКАЦИЯ В ОСНОВНУЮ ГРУППУ ----
        screens = data["screens"]

        caption = (
            f"✅ {'Контракт' if req_type == 'contract' else 'Семья'} ОДОБРЕН\n"
            f"👤 {nick}\n"
            f"👔 {users[nick]['role']}"
        )

        media = [
            InputMediaPhoto(open(screens[0], "rb"), caption=caption),
            InputMediaPhoto(open(screens[1], "rb"))
        ]

        await context.bot.send_media_group(GROUP_ID, media)

        await context.bot.send_message(
            data["chat_id"],
            "✅ Руководство одобрило вашу заявку."
        )

        pending.pop(req_id)
        save_pending(pending)

        await query.message.reply_text("✅ Заявка одобрена и опубликована.")

    elif action == "reject":
        context.chat_data["reject_id"] = req_id
        await query.message.reply_text("❌ Напишите причину отказа одним сообщением:")

# ================= REJECT REASON =================
async def reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req_id = context.chat_data.get("reject_id")
    if not req_id or req_id not in pending:
        return

    data = pending.pop(req_id)
    save_pending(pending)

    await context.bot.send_message(
        data["chat_id"],
        f"❌ Ваша заявка отклонена.\n\nПричина:\n{update.message.text}"
    )

    context.chat_data.pop("reject_id", None)
    await update.message.reply_text("🚫 Отказ отправлён пользователю.")

# ================= MAIN =================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.GROUPS,
        reject_reason
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(
            "^(📊 Общая статистика|➕ Добавить контракт|👨‍👩‍👧 Добавить семью|📈 UMO статистика)$"
        ),
        menu_handler
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        auth
    ))

    app.add_handler(MessageHandler(filters.PHOTO, photos))
    app.add_handler(CallbackQueryHandler(callbacks))

    app.run_polling()

if __name__ == "__main__":
    main()

