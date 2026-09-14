import os

from dotenv import load_dotenv
from anthropic import Anthropic
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# .env faylini yuklash
load_dotenv()

# API key va Telegram tokenni olish
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Claude client
claude = Anthropic(api_key=ANTHROPIC_API_KEY)


# /start komandasi
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom, Asadbek! 👋\n\n"
        "Men sizning personal AI assistant'ingizman.\n"
        "Menga oddiy xabar yuboring."
    )


# Oddiy Telegram xabarlarini qabul qilish
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text

    try:
        response = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=(
                "You are a personal AI assistant for Asadbek. "
                "Respond in Uzbek unless the user asks for another language. "
                "Be clear, practical, concise, and helpful."
            ),
            messages=[
                {
                    "role": "user",
                    "content": user_message,
                }
            ],
        )

        answer = response.content[0].text

        await update.message.reply_text(answer)

    except Exception as e:
        print(f"ERROR: {e}")

        await update.message.reply_text(
            "Kechirasiz, hozir texnik xatolik yuz berdi. "
            "Bir ozdan keyin qayta urinib ko‘ring."
        )


# Botni ishga tushirish
def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("🤖 Personal AI Agent ishga tushdi!")
    print("Telegram botga xabar yuborishingiz mumkin.")

    application.run_polling()


if __name__ == "__main__":
    main()
    