import os

from telebot import types

token = os.getenv("TELEGRAM_BOT_TOKEN", "")
botusername = os.getenv("TELEGRAM_BOT_USERNAME", "").lstrip("@")
coinbase_api_key = os.getenv("COINBASE_API_KEY", "")
cc_secret_header = os.getenv("COINBASE_WEBHOOK_SECRET", "")
dummychatid = int(os.getenv("ADMIN_CHAT_ID", "0"))
storagechatid = int(os.getenv("STORAGE_CHAT_ID", "0"))
permissions_photo_id = int(os.getenv("PERMISSIONS_PHOTO_ID", "0"))
public_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
redirect_url = os.getenv("PAYMENT_REDIRECT_URL") or (
    f"{public_url}/payment-success" if public_url else ""
)
cancel_url = os.getenv("PAYMENT_CANCEL_URL") or (
    f"{public_url}/payment-cancel" if public_url else ""
)
percent = float(os.getenv("PLATFORM_SHARE", "0"))
withmin = float(os.getenv("MIN_WITHDRAWAL_USD", "10"))
telegram_webhook_path = os.getenv("TELEGRAM_WEBHOOK_PATH", "/telegram-webhook")
if not telegram_webhook_path.startswith("/"):
    telegram_webhook_path = f"/{telegram_webhook_path}"
telegram_webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
coinbase_webhook_path = os.getenv("COINBASE_WEBHOOK_PATH", "/coinbase-webhook")
if not coinbase_webhook_path.startswith("/"):
    coinbase_webhook_path = f"/{coinbase_webhook_path}"
daily_tasks_token = os.getenv("DAILY_TASKS_TOKEN", "")

starttext = "Welcome. Choose an option below."

startmarkup = types.ReplyKeyboardMarkup(resize_keyboard=True)
startmarkup.row("My Chats", "New")
startmarkup.row("My Subscriptions", "Wallet")
startmarkup.row("Support")

cancel = types.ReplyKeyboardMarkup(resize_keyboard=True)
cancel.add("Cancel")

donecancel = types.ReplyKeyboardMarkup(resize_keyboard=True)
donecancel.row("Done", "Cancel")

walletmarkup = types.ReplyKeyboardMarkup(resize_keyboard=True)
walletmarkup.row("Deposit", "Withdraw")
walletmarkup.add("Back")


def userchattext(group, chat, auto=False):
    return (
        f"{chat.title}\nMonthly price: ${group.cost:.2f}"
        + ("\nMigration access" if auto else "")
    )


def userchatmarkup(chat_id, action=None, auto=False):
    markup = types.InlineKeyboardMarkup()
    if auto:
        markup.add(
            types.InlineKeyboardButton(
                "Join", callback_data=f"auto:{chat_id[0]}:{chat_id[1]}"
            )
        )
    elif action == "unsub":
        markup.add(
            types.InlineKeyboardButton(
                "Unsubscribe", callback_data=f"rmv:{chat_id}"
            )
        )
    else:
        markup.add(
            types.InlineKeyboardButton("Subscribe", callback_data=f"add:{chat_id}")
        )
    return markup


def mychattext(group, chat):
    return f"{chat.title}\nMonthly price: ${group.cost:.2f}"


def mychatmarkup(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("Share link", callback_data=f"glink:{chat_id}"),
        types.InlineKeyboardButton("Remove", callback_data=f"del:{chat_id}"),
    )
    return markup


def yesnomarkup(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("Yes", callback_data=f"rmvyes:{chat_id}"),
        types.InlineKeyboardButton("No", callback_data=f"rmvno:{chat_id}"),
    )
    return markup


def yesnomarkup1(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("Yes", callback_data=f"delyes:{chat_id}"),
        types.InlineKeyboardButton("No", callback_data=f"delno:{chat_id}"),
    )
    return markup


def wfinalmarkup(user_id, amount):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(
            "Approve", callback_data=f"paid:{user_id}:{amount}"
        ),
        types.InlineKeyboardButton(
            "Refund", callback_data=f"refund:{user_id}:{amount}"
        ),
    )
    return markup
