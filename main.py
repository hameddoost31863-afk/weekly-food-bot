import logging
import sqlite3
import pandas as pd
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = "8539930547:AAHBkgBTf3LMxEAnbBHnUb3Vu1Y_Zv1B9uY"
DB_PATH = "menu_bot.db"
EXCEL_PATH = "orders.xlsx"

# منوی هفتگی
WEEK_MENU = {
    "شنبه": ["چلو مرغ زعفرانی", "کشمش پلو با گوشت قلقلی", "خوراک مرغ", "غذای گیاهی"],
    "یکشنبه": ["چلو جوجه کباب", "سبزی پلو با گوشت", "خوراک مرغ", "غذای گیاهی"],
    "دوشنبه": ["چلو مرغ", "لوبیا پلو با گوشت و ماست", "خوراک مرغ", "غذای گیاهی"],
    "سه‌شنبه": ["چلو خورشت قورمه‌سبزی", "چلو گوشت", "خوراک مرغ", "غذای گیاهی"],
    "چهارشنبه": ["سبزی پلو با مرغ", "آبگوشت", "خوراک مرغ", "غذای گیاهی"],
    "پنجشنبه": ["چلو کباب کوبیده", "چلو مرغ زعفرانی", "خوراک مرغ", "غذای گیاهی"],
    "جمعه": ["چلو خورشت قیمه", "ماکارونی با گوشت و ماست", "خوراک مرغ", "غذای گیاهی"]
}

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# دیتابیس
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS choices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        full_name TEXT,
        day TEXT,
        food TEXT,
        ts TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.commit()
    conn.close()

def set_admin(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", ("admin_id", str(user_id)))
    conn.commit()
    conn.close()

def get_admin():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM meta WHERE key = ?", ("admin_id",))
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else None

def save_choice(user_id, username, full_name, day, food):
    ts = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM choices WHERE user_id = ? AND day = ?", (user_id, day))
    row = c.fetchone()
    if row:
        c.execute("UPDATE choices SET food = ?, ts = ?, username = ?, full_name = ? WHERE id = ?",
                  (food, ts, username, full_name, row[0]))
    else:
        c.execute("INSERT INTO choices (user_id, username, full_name, day, food, ts) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, username, full_name, day, food, ts))
    conn.commit()
    conn.close()

def get_all_choices():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT user_id, username, full_name, day, food, ts FROM choices", conn)
    conn.close()
    return df

# گرفتن روز بعد
def next_day_fa():
    days_fa = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
    today_index = datetime.now().weekday()  # 0=Monday
    mapping = [6,0,1,2,3,4,5]  # تبدیل به index شنبه=0
    today_fa_index = mapping[today_index]
    next_index = (today_fa_index + 1) % 7
    return days_fa[next_index]

# هندلرها
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day = next_day_fa()
    foods = WEEK_MENU[day]
    keyboard = [[InlineKeyboardButton(food, callback_data=f"food|{day}|{food}")] for food in foods]
    await update.effective_chat.send_message(f"سلام! لطفاً غذای روز بعد ({day}) را انتخاب کنید:",
                                             reply_markup=InlineKeyboardMarkup(keyboard))

async def select_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, day, food = query.data.split("|")
    user = query.from_user
    username = user.username or ""
    full_name = (user.first_name or "") + (" " + user.last_name if user.last_name else "")
    save_choice(user.id, username, full_name.strip(), day, food)
    await query.edit_message_text(text=f"✔️ انتخاب شما برای *{day}* ثبت شد:\n*{food}*", parse_mode="Markdown")

async def setadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    set_admin(user.id)
    await update.effective_chat.send_message(f"✅ کاربر `{user.id}` به‌عنوان ادمین ثبت شد. (نام: {user.full_name})", parse_mode="Markdown")

async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user
    admin_id = get_admin()
    if admin_id is None:
        await update.effective_chat.send_message("⚠️ هنوز ادمینی تعیین نشده. ابتدا /setadmin را اجرا کن.")
        return
    if caller.id != admin_id:
        await update.effective_chat.send_message("❌ فقط ادمین می‌تواند خروجی اکسل را دریافت کند.")
        return
    df = get_all_choices()
    if df.empty:
        await update.effective_chat.send_message("هیچ سفارشی ثبت نشده است.")
        return
    df = df.sort_values(by=["day", "full_name"])
    df.to_excel(EXCEL_PATH, index=False)
    with open(EXCEL_PATH, "rb") as f:
        await update.effective_chat.send_document(document=f, filename=EXCEL_PATH, caption="فایل اکسل سفارش‌ها")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message("دستور شناخته‌شده‌ای نیست. از دکمه‌ها استفاده کن یا /start.")

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setadmin", setadmin_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CallbackQueryHandler(select_food, pattern=r"^food\\|"))
    app.run_polling()

if __name__ == "__main__":
    main()
