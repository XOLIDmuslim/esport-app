import os
import sys
import re
import random
import sqlite3
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    MenuButtonWebApp,
    MenuButtonDefault,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==========================================================
# ⚙️ SOZLAMALAR & KONFIGURATSIYA
# ==========================================================
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "8984344293:AAEq7-88TJeYW5ub3JZ0Ub2568_b4curiYk")
SUPER_ADMIN_ID = int(os.getenv("ADMIN_ID", "5921750089"))
SUPER_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "Muhammad_Xol1d").replace("@", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "")

DB_PATH = "pubg_bot.db"

# ==========================================================
# 🗄️ BAZA BILAN ISHLASH (SQLite)
# ==========================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Foydalanuvchilar
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Xalifalik ma'murlari (Saidlar)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'said',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Majburiy obuna kanallari
    cur.execute("""
        CREATE TABLE IF NOT EXISTS force_channels (
            channel_id TEXT PRIMARY KEY,
            title TEXT,
            invite_link TEXT
        )
    """)
    # Taklif va fikrlar
    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedbacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # VIP Optimizatsiya buyurtmalari
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            device_model TEXT,
            fps_target TEXT,
            contact TEXT,
            status TEXT DEFAULT 'yangi',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Xabar bog'lamasi: Admin javob qaytarganda foydalanuvchiga yuborish uchun
    cur.execute("""
        CREATE TABLE IF NOT EXISTS message_map (
            admin_msg_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            original_msg_id INTEGER
        )
    """)
    
    # Super Adminni avtomatik qo'shish
    cur.execute("INSERT OR IGNORE INTO admins (user_id, role) VALUES (?, 'xalifa')", (SUPER_ADMIN_ID,))
    conn.commit()
    conn.close()

init_db()

def save_user(user_id: int, username: str, full_name: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username=?, full_name=?
        """, (user_id, username, full_name, username, full_name))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Baza xatosi (save_user): {e}")

def is_admin(user_id: int) -> bool:
    if user_id == SUPER_ADMIN_ID:
        return True
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    res = cur.fetchone()
    conn.close()
    return bool(res)

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM feedbacks")
    total_feedbacks = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM orders")
    total_orders = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM force_channels")
    total_channels = cur.fetchone()[0]
    conn.close()
    return {
        "users": total_users,
        "feedbacks": total_feedbacks,
        "orders": total_orders,
        "channels": total_channels,
    }

# ==========================================================
# 🛑 SO'KINISH VA NOJO'YA SO'ZLAR FILTRI (PROFANITY FILTER)
# ==========================================================
BAD_WORDS = [
    r"sik", r"jalap", r"qotoq", r"am", r"dalbayob", r"blyad", r"suka", r"gandon",
    r"chumo", r"itvachcha", r"onangni", r"padar", r"yebsan", r"qo'toq", r"shilta",
    r"хуй", r"пизд", r"ебат", r"бля", r"сука", r"гандон", r"долбо", r"член"
]

def contains_profanity(text: str) -> bool:
    low = text.lower()
    for pattern in BAD_WORDS:
        if re.search(r"\b" + pattern, low) or pattern in low:
            return True
    return False

# ==========================================================
# 🌐 24/7 CLOUD / RENDER HEALTH SERVER
# ==========================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"PUBG Mobile Pro Bot & Mini App Gateway is 24/7 Active!")

    def log_message(self, format, *args):
        pass

def start_health_server():
    port = int(os.environ.get("PORT", 0))
    if port > 0:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"24/7 Health Server {port}-portda ishga tushdi.", flush=True)

# ==========================================================
# 📱 ASOSIY MENYU TUGMALARI
# ==========================================================
def get_main_reply_keyboard(user_id: int):
    keyboard = [
        [KeyboardButton("⚡ Optimizatsiya (Pullik VIP)"), KeyboardButton("💳 Donat qilish (Qo'llash)")],
        [KeyboardButton("💬 Adminga xabar"), KeyboardButton("💡 Takliflar")],
        [KeyboardButton("📱 Telegram"), KeyboardButton("📸 Instagram"), KeyboardButton("▶️ YouTube")],
    ]
    if is_admin(user_id):
        keyboard.append([KeyboardButton("👑 Xalifalik (Admin Panel)")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_sub_channels():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT channel_id, title, invite_link FROM force_channels")
    rows = cur.fetchall()
    conn.close()
    return rows

async def check_user_subscriptions(user_id: int, bot) -> list:
    channels = get_sub_channels()
    unsubscribed = []
    for cid, title, link in channels:
        try:
            member = await bot.get_chat_member(chat_id=cid, user_id=user_id)
            if member.status in ["left", "kicked"]:
                unsubscribed.append((cid, title, link))
        except Exception:
            # Agar bot kanalda admin bo'lmasa yoki kanal topilmasa
            pass
    return unsubscribed

# ==========================================================
# 🚀 /START BUYRUG'I VA SALOMLASHUV
# ==========================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username or "", user.full_name or "")
    
    # 1. Majburiy obuna tekshiruvi (agar kanallar mavjud bo'lsa)
    unsub = await check_user_subscriptions(user.id, context.bot)
    if unsub:
        buttons = []
        for cid, title, link in unsub:
            buttons.append([InlineKeyboardButton(f"➕ {title}", url=link)])
        buttons.append([InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")])
        await update.message.reply_text(
            f"Hurmatli <b>@{user.username or user.first_name}</b>!\n\n"
            f"Botdan to'liq foydalanish va eng yangi kiber nastroykalarni olish uchun "
            f"quyidagi rasmiy kanallarimizga obuna bo'ling:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    user_mention = f"@{user.username}" if user.username else f"<b>{user.first_name}</b>"

    greeting_text = (
        f"Assalomu alaykum, {user_mention}! 🎯\n\n"
        f"🔥 <b>PUBG MOBILE PRO OPTIMIZER & SENS ANALYZER</b> rasmiy tizimiga xush kelibsiz!\n\n"
        f"📌 <b>Botning asosiy vazifasi va sizga taqdim etadigan yechimi:</b>\n"
        f"Siz bu yerda o'z qurilmangiz uchun 100% individual <b>Chust (Sens)</b> va professional "
        f"<b>takomillashgan boshqaruv nastroykalarini</b> yasay olasiz!\n\n"
        f"🎮 <b>ESPORT APP:</b> Ekraningizning chap pastki burchagidagi <b>«ESPORT APP»</b> menyusi orqali "
        f"ilovamizga kiring va o'z telefoningiz parametrlarini kiber darajada hisoblang!\n\n"
        f"🚀 <i>Biz bilan o'yiningizni yangi bosqichga olib chiqing. Har bir g'alaba to'g'ri sozlangan nazoratdan boshlanadi!</i>"
    )

    inline_kb = [
        [InlineKeyboardButton("📱 Telegram Kanal", url="https://t.me/XOLID_PUBGM")],
        [
            InlineKeyboardButton("📸 Instagram", url="https://www.instagram.com/xol1dmuslim/"),
            InlineKeyboardButton("▶️ YouTube", url="https://www.youtube.com/@XOLID_PUBGMonlywww"),
        ],
    ]
    if MINI_APP_URL:
        inline_kb.insert(0, [InlineKeyboardButton("🎮 ESPORT APP (Mini App)", web_app=WebAppInfo(url=MINI_APP_URL))])

    await update.message.reply_text(
        greeting_text,
        parse_mode="HTML",
        reply_markup=get_main_reply_keyboard(user.id),
    )
    await update.message.reply_text(
        "👇 Quyidagi rasmiy tarmoqlarimizga a'zo bo'ling va eng so'nggi sirlardan boxabar bo'ling:",
        reply_markup=InlineKeyboardMarkup(inline_kb),
    )

# ==========================================================
# ⚡ OPTIMIZATSIYA (PULLIK VIP) BO'LIMI
# ==========================================================
def get_optimization_keyboard():
    buttons = [
        [InlineKeyboardButton("🍎 iPhone (iOS) — 90/120 FPS Stabilizatsiya", callback_data="opt_iphone")],
        [InlineKeyboardButton("📱 Poco / Xiaomi / Redmi — Qizish va Drosselni olish", callback_data="opt_poco")],
        [InlineKeyboardButton("📱 Samsung Galaxy — GOS o'chirish & FPS Boost", callback_data="opt_samsung")],
        [InlineKeyboardButton("📱 Boshqa Android (Realme/Infinix/Tecno)", callback_data="opt_other")],
        [InlineKeyboardButton("🔥 VIP Individual Nastroyka Buyurtma Qilish", callback_data="opt_order_start")],
    ]
    return InlineKeyboardMarkup(buttons)

async def handle_optimization_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        f"⚡ <b>PUBG MOBILE PRO OPTIMIZATSIYA XIZMATI (PULLIK VIP)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Telefoningizda qotish (lag), FPS tushishi, drossel yoki qizish bormi? "
        f"Biz har bir telefon protsessori va operatsion tizimiga moslashtirilgan <b>chuqur professional optimizatsiya</b> taqdim etamiz!\n\n"
        f"💎 <b>Nimalar qilinadi:</b>\n"
        f"• CPU & GPU drosselini (qizib tezlik pasayishini) to'xtatish\n"
        f"• Keraksiz tizim jarayonlarini (bloatware) tozalash\n"
        f"• Barqaror 60 / 90 / 120 FPS fiksatsiyasi\n"
        f"• Sensor va ekranning kechikishini (Touch Latency) pasaytirish\n"
        f"• Qurilmangizga 100% individual Chust va Giroskop kalibrovkasi\n\n"
        f"Modellardan birini tanlang yoki VIP buyurtma bering:"
    )
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=get_optimization_keyboard())

# ==========================================================
# 💳 DONAT QILISH (QO'LLAB-QUVVATLASH)
# ==========================================================
def get_donation_keyboard():
    buttons = [
        [
            InlineKeyboardButton("💳 Uzcard / Humo", callback_data="don_card"),
            InlineKeyboardButton("📱 Click / Payme", callback_data="don_click_payme"),
        ],
        [
            InlineKeyboardButton("💎 USDT (Crypto TRC-20 / TON)", callback_data="don_crypto"),
            InlineKeyboardButton("⭐ Telegram Stars", callback_data="don_stars"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)

async def handle_donation_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        f"❤️ <b>LOYIHANI QO'LLAB-QUVVATLASH (DONAT)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Bizning PUBG Mobile Pro Optimizer tizimimiz har bir o'yinchiga bepul va sifatli "
        f"kiber parametrlar taqdim etib kelmoqda.\n\n"
        f"Agar loyihamiz sizga foyda keltirgan bo'lsa va bot rivojiga o'z hissangizni qo'shmoqchi bo'lsangiz, "
        f"quyidagi qulay usullardan biri orqali donat qilishingiz mumkin. "
        f"Har bir yordam server xarajatlari va yangi funksiyalarni rivojlantirishga sarflanadi!\n\n"
        f"👇 <b>To'lov turini tanlang:</b>"
    )
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=get_donation_keyboard())

# ==========================================================
# 💬 ADMINGA XABAR (2-WAY SUPPORT CHAT)
# ==========================================================
async def handle_admin_chat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "awaiting_support_message"
    txt = (
        f"💬 <b>ADMINGA XABAR YO'LLASH</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Savolingiz, muammo yoki buyurtmangiz bo'yicha to'g'ridan-to'g'ri xabar qoldiring.\n\n"
        f"⚠️ <i>Eslatma: Xabaringiz bot orqali ma'muriyatga xavfsiz yetkaziladi va administrator javobini "
        f"ham bevosita shu yerda qabul qilasiz (Shaxsiy lichkaga o'tish shart emas).</i>\n\n"
        f"✍️ <b>Xabaringizni yozib yuboring (yoki bekor qilish uchun /cancel bosing):</b>"
    )
    await update.message.reply_text(txt, parse_mode="HTML")

# ==========================================================
# 💡 TAKLIFLAR (SUGGESTIONS WITH PROFANITY FILTER)
# ==========================================================
async def handle_suggestions_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "awaiting_feedback"
    txt = (
        f"💡 <b>BOT BO'YICHA TAKLIF VA FIKRLAR</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Botimizni yanada mukammal qilish uchun qanday g'oyalaringiz bor? "
        f"Qaysi funksiya yoki yangi telefon parametrlarini qo'shishimizni xohlaysiz?\n\n"
        f"Barcha takliflar alohida kanalimizga va rahbariyatga to'g'ridan-to'g'ri yuboriladi.\n\n"
        f"🛡️ <i>Tizimda odob-axloq filtri o'rnatilgan. Haqorat va behayo so'zlar qat'iyan man etiladi.</i>\n\n"
        f"✍️ <b>Taklifingizni matn ko'rinishida yozib yuboring:</b>"
    )
    await update.message.reply_text(txt, parse_mode="HTML")

# ==========================================================
# 👑 XALIFALIK (ADMIN PANEL)
# ==========================================================
def get_xalifalik_keyboard(is_super_admin: bool):
    buttons = [
        [InlineKeyboardButton("📊 Umumiy Statistika", callback_data="xalifa_stats")],
        [InlineKeyboardButton("📢 Hammaga Xabar (Broadcast)", callback_data="xalifa_broadcast")],
        [InlineKeyboardButton("⚡ VIP Buyurtmalar Ro'yxati", callback_data="xalifa_orders")],
        [InlineKeyboardButton("💡 Foydalanuvchilar Takliflari", callback_data="xalifa_feedbacks")],
        [InlineKeyboardButton("➕ Majburiy Kanal Qo'shish/O'chirish", callback_data="xalifa_channels")],
    ]
    if is_super_admin:
        buttons.append([InlineKeyboardButton("👥 Saidlarni Boshqarish (Yordamchi Adminlar)", callback_data="xalifa_manage_saids")])
    return InlineKeyboardMarkup(buttons)

async def handle_xalifalik_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Sizda ushbu maxfiy bo'limga kirish huquqi yo'q!")
        return

    is_super = (user_id == SUPER_ADMIN_ID)
    role_name = "Xalifa (Bosh Administrator)" if is_super else "Said (Administrator)"
    
    txt = (
        f"👑 <b>XALIFALIK BOSHQARUV MARKAZI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Assalomu alaykum, muhtaram <b>{role_name}</b>!\n\n"
        f"Tizim to'liq sizning nazoratingiz ostida. Quyidagi menyu orqali "
        f"bot foydalanuvchilarini, buyurtmalarni va kanallarni boshqarishingiz mumkin:"
    )
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=get_xalifalik_keyboard(is_super))

# ==========================================================
# 📩 FOYDALANUVCHI MATNLARI & ADMIN JAVOBLARI (MESSAGE HANDLER)
# ==========================================================
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    user = update.effective_user
    text = msg.text.strip()
    state = context.user_data.get("state")

    # 1. Reply keyboard tugmalari tekshiruvi
    if text == "⚡ Optimizatsiya (Pullik VIP)":
        context.user_data["state"] = None
        await handle_optimization_menu(update, context)
        return
    elif text == "💳 Donat qilish (Qo'llash)":
        context.user_data["state"] = None
        await handle_donation_menu(update, context)
        return
    elif text == "💬 Adminga xabar":
        await handle_admin_chat_start(update, context)
        return
    elif text == "💡 Takliflar":
        await handle_suggestions_start(update, context)
        return
    elif text == "📱 Telegram":
        await msg.reply_text(
            "📱 <b>Bizning rasmiy Telegram kanalimiz:</b>\n👉 https://t.me/XOLID_PUBGM\n\nObuna bo'ling va eng so'nggi yangiliklardan orqada qolmang!",
            parse_mode="HTML",
            disable_web_page_preview=False,
        )
        return
    elif text == "📸 Instagram":
        await msg.reply_text(
            "📸 <b>Bizning rasmiy Instagram profilimiz:</b>\n👉 https://www.instagram.com/xol1dmuslim/\n\nObuna bo'lib, eng daxshatli kiber fragmovie va maslahatlarni kuzatib boring!",
            parse_mode="HTML",
            disable_web_page_preview=False,
        )
        return
    elif text == "▶️ YouTube":
        await msg.reply_text(
            "▶️ <b>Bizning rasmiy YouTube kanalimiz:</b>\n👉 https://www.youtube.com/@XOLID_PUBGMonlywww\n\nVideolarga layk bosing va pro sozlamalar bo'yicha videolarni tomosha qiling!",
            parse_mode="HTML",
            disable_web_page_preview=False,
        )
        return
    elif text == "👑 Xalifalik (Admin Panel)":
        context.user_data["state"] = None
        await handle_xalifalik_panel(update, context)
        return

    # 2. Agar Admin foydalanuvchi xabariga "Reply" qilib javob yozgan bo'lsa
    if is_admin(user.id) and msg.reply_to_message:
        replied_id = msg.reply_to_message.message_id
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT user_id, original_msg_id FROM message_map WHERE admin_msg_id = ?", (replied_id,))
        row = cur.fetchone()
        conn.close()

        if row:
            target_user_id, original_msg_id = row
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"💬 <b>Ma'muriyatdan javob:</b>\n\n{text}",
                    parse_mode="HTML",
                    reply_to_message_id=original_msg_id,
                )
                await msg.reply_text("✅ Javobingiz foydalanuvchiga muvaffaqiyatli yetkazildi!")
                return
            except Exception as e:
                await msg.reply_text(f"❌ Xabar yuborishda xatolik: {e}")
                return

    # 3. State: Adminga xabar yo'llash
    if state == "awaiting_support_message":
        if text.startswith("/"):
            context.user_data["state"] = None
            await msg.reply_text("Jarayon bekor qilindi.")
            return

        # So'kinish tekshiruvi
        if contains_profanity(text):
            await msg.reply_text("⚠️ Iltimos, xabaringizda haqoratomuz so'zlardan foydalanmang! Qaytadan xushmuomalalik bilan yozing:")
            return

        context.user_data["state"] = None
        
        # Super Adminga va Saidlarga xabar yuborish
        admin_text = (
            f"📩 <b>YANGI MUROJAAT (Adminga xabar)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Kimdan:</b> {user.full_name} (@{user.username or 'yoq'})\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"⏰ <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"📝 <b>Xabar matni:</b>\n{text}\n\n"
            f"<i>💡 Javob berish uchun ushbu xabarga 'Reply' qilib yozing!</i>"
        )

        try:
            admin_msg = await context.bot.send_message(
                chat_id=SUPER_ADMIN_ID,
                text=admin_text,
                parse_mode="HTML"
            )
            # Map saqlash
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO message_map (admin_msg_id, user_id, original_msg_id) VALUES (?, ?, ?)",
                (admin_msg.message_id, user.id, msg.message_id)
            )
            conn.commit()
            conn.close()

            await msg.reply_text(
                "✅ <b>Xabaringiz ma'muriyatga qabul qilindi!</b>\n\n"
                "Tez orada administratorlarimiz ko'rib chiqib, to'g'ridan-to'g'ri bot orqali sizga javob yuborishadi.",
                parse_mode="HTML"
            )
        except Exception as e:
            await msg.reply_text(f"❌ Xatolik yuz berdi: {e}")
        return

    # 4. State: Takliflar (Feedback)
    if state == "awaiting_feedback":
        if text.startswith("/"):
            context.user_data["state"] = None
            await msg.reply_text("Jarayon bekor qilindi.")
            return

        if contains_profanity(text):
            await msg.reply_text(
                "🚫 <b>Diqqat:</b> Taklifingizda qabul qilib bo'lmaydigan so'zlar aniqlandi.\n"
                "Iltimos, g'oya va mulohazalaringizni madaniy tilda bayon eting:",
                parse_mode="HTML"
            )
            return

        context.user_data["state"] = None
        
        # Bazaga saqlash
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO feedbacks (user_id, username, text) VALUES (?, ?, ?)",
            (user.id, user.username or "", text)
        )
        conn.commit()
        conn.close()

        # Adminga xabarnoma yuborish
        notify_admin = (
            f"💡 <b>YANGI TAKLIF KELIB TUSHDI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Foydalanuvchi:</b> {user.full_name} (@{user.username or 'yoq'})\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n\n"
            f"💬 <b>Taklif:</b>\n{text}"
        )
        try:
            await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=notify_admin, parse_mode="HTML")
        except Exception:
            pass

        await msg.reply_text(
            "💎 <b>Katta rahmat!</b>\n\n"
            "Sizning taklifingiz qabul qilindi va ma'muriyatga yetkazildi. "
            "Botimizni siz kabi faol o'yinchilar bilan birgalikda eng cho'qqiga olib chiqamiz!",
            parse_mode="HTML"
        )
        return

    # 5. State: VIP Optimizatsiya buyurtmasi qabul qilish
    if state == "order_device":
        context.user_data["order_device"] = text
        context.user_data["state"] = "order_fps"
        await msg.reply_text(
            "🎯 Telefoningiz hozir nechchi FPS beradi va qancha FPS olmoqchisiz? (Masalan: 45 dan 60 ga, yoki 60 dan 90 ga):"
        )
        return

    if state == "order_fps":
        context.user_data["order_fps"] = text
        context.user_data["state"] = "order_contact"
        await msg.reply_text(
            "📞 Siz bilan bog'lanish uchun telefon raqamingiz yoki Telegram username kiriting:"
        )
        return

    if state == "order_contact":
        contact_info = text
        device_model = context.user_data.get("order_device", "Noma'lum")
        fps_target = context.user_data.get("order_fps", "Noma'lum")
        context.user_data["state"] = None

        # Bazaga yozish
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (user_id, username, device_model, fps_target, contact) VALUES (?, ?, ?, ?, ?)",
            (user.id, user.username or "", device_model, fps_target, contact_info)
        )
        conn.commit()
        conn.close()

        # Adminga jo'natish
        admin_alert = (
            f"🔥 <b>YANGI VIP OPTIMIZATSIYA BUYURTMASI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Mijoz:</b> {user.full_name} (@{user.username or 'yoq'})\n"
            f"📱 <b>Telefon modeli:</b> {device_model}\n"
            f"⚡ <b>FPS maqsadi:</b> {fps_target}\n"
            f"📞 <b>Aloqa:</b> {contact_info}\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>"
        )
        try:
            await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=admin_alert, parse_mode="HTML")
        except Exception:
            pass

        await msg.reply_text(
            "🎉 <b>Buyurtmangiz muvaffaqiyatli qabul qilindi!</b>\n\n"
            "Mutaxassisimiz tez orada siz bilan bog'lanadi va qurilmangizni maksimal darajada sozlash jarayonini boshlaydi.",
            parse_mode="HTML"
        )
        return

    # 6. Admin Panel States (Broadcast, Said qo'shish, Kanal qo'shish)
    if is_admin(user.id):
        if state == "broadcast_text":
            context.user_data["state"] = None
            await msg.reply_text("⏳ Xabar barcha foydalanuvchilarga tarqatilmoqda...")
            
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM users")
            all_users = cur.fetchall()
            conn.close()

            success = 0
            fail = 0
            for (uid,) in all_users:
                try:
                    await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat_id, message_id=msg.message_id)
                    success += 1
                except Exception:
                    fail += 1

            await msg.reply_text(
                f"📢 <b>Tarqatish yakunlandi!</b>\n\n"
                f"✅ Yetkazildi: {success} ta\n"
                f"❌ Xatolik (bloklaganlar): {fail} ta",
                parse_mode="HTML"
            )
            return

        if state == "add_said_id":
            context.user_data["state"] = None
            try:
                new_admin_id = int(text)
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO admins (user_id, role) VALUES (?, 'said')", (new_admin_id,))
                conn.commit()
                conn.close()
                await msg.reply_text(f"✅ Yangi Said (Administrator) muvaffaqiyatli tayinlandi: <code>{new_admin_id}</code>", parse_mode="HTML")
            except ValueError:
                await msg.reply_text("❌ Faqat sonli Telegram ID kiriting!")
            return

        if state == "add_channel":
            # Format: @kanal_username yoki -100xxx | Sarlavha | Havola
            context.user_data["state"] = None
            parts = [p.strip() for p in text.split("|")]
            if len(parts) >= 3:
                cid, title, link = parts[0], parts[1], parts[2]
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO force_channels (channel_id, title, invite_link) VALUES (?, ?, ?)", (cid, title, link))
                conn.commit()
                conn.close()
                await msg.reply_text(f"✅ Majburiy obuna kanali qo'shildi:\n<b>{title}</b> ({cid})", parse_mode="HTML")
            else:
                await msg.reply_text("❌ Noto'g'ri format! Format: <code>@kanal | Sarlavha | https://t.me/link</code> ko'rinishida yuboring.", parse_mode="HTML")
            return

# ==========================================================
# 🎮 CALLBACK QUERY HANDLER
# ==========================================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    # 1. Obunani qayta tekshirish
    if data == "check_sub":
        unsub = await check_user_subscriptions(user.id, context.bot)
        if unsub:
            await query.answer("❌ Hali hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)
        else:
            await query.edit_message_text("✅ Rahmat! Barcha kanallarga a'zo bo'ldingiz. Endi botdan to'liq foydalanishingiz mumkin.")
            # Start qayta chaqirish
            user_mention = f"@{user.username}" if user.username else f"<b>{user.first_name}</b>"
            txt = (
                f"Assalomu alaykum, {user_mention}! 🎯\n\n"
                f"🔥 <b>PUBG MOBILE PRO OPTIMIZER</b> ga xush kelibsiz!\n"
                f"Pastdagi <b>«ESPORT APP»</b> tugmasi orqali ilovani ochishingiz yoki pastdagi menyulardan foydalanishingiz mumkin."
            )
            await query.message.reply_text(txt, parse_mode="HTML", reply_markup=get_main_reply_keyboard(user.id))

    # 2. Donat tafsilotlari
    elif data == "don_card":
        txt = (
            f"💳 <b>UZCARD & HUMO KARTALARI:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• Karta: <code>8600 0000 0000 0000</code>\n"
            f"• Egasining ismi: <b>XOLID M.</b>\n\n"
            f"<i>💡 Donat qilganingizdan so'ng chekni 'Adminga xabar' bo'limi orqali yuborishingiz mumkin! Rahmat!</i>"
        )
        await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ortga", callback_data="don_back")]]))

    elif data == "don_click_payme":
        txt = (
            f"📱 <b>CLICK & PAYME TO'LOV:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• Telefon raqam: <code>+998 90 000 00 00</code>\n"
            f"• Qabul qiluvchi: <b>Muhammad Xolid</b>\n\n"
            f"Click yoki Payme ilovasidan 'Telefon raqamiga o'tkazish' orqali o'tkazishingiz mumkin."
        )
        await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ortga", callback_data="don_back")]]))

    elif data == "don_crypto":
        txt = (
            f"💎 <b>USDT / KRIPTOVALYUTA:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>USDT (TRC-20):</b>\n<code>TY2aB1q8XoLidPubgExampleTronAddress...</code>\n\n"
            f"• <b>USDT (TON):</b>\n<code>EQD2_XolidPubgTonNetworkAddress...</code>\n\n"
            f"<i>Bitta bosish orqali manzilni nusxalab oling.</i>"
        )
        await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ortga", callback_data="don_back")]]))

    elif data == "don_stars":
        txt = (
            f"⭐ <b>TELEGRAM STARS (YULDUZLAR):</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Tez orada to'g'ridan-to'g'ri Telegram Stars orqali qo'llab-quvvatlash imkoni qo'shiladi!"
        )
        await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ortga", callback_data="don_back")]]))

    elif data == "don_back":
        txt = (
            f"❤️ <b>LOYIHANI QO'LLAB-QUVVATLASH (DONAT)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Quyidagi qulay usullardan birini tanlang:"
        )
        await query.edit_message_text(txt, parse_mode="HTML", reply_markup=get_donation_keyboard())

    # 3. Optimizatsiya tafsilotlari
    elif data == "opt_iphone":
        txt = (
            f"🍎 <b>IPHONE (iOS) PRO OPTIMIZATSIYA:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• ProMotion 120Hz silliqligini fiksatsiya qilish\n"
            f"• Ekran yorug'ligi tushib ketishini (Dimming) to'xtatish\n"
            f"• Batareya qizishini kamaytirish va Touch-Sensors reaksiyasini oshirish\n"
            f"• Individual Chust + Bulut kodi taqdim etiladi\n\n"
            f"💰 Narxi: <b>Kelishilgan holda</b>"
        )
        btn = [
            [InlineKeyboardButton("🔥 VIP Buyurtma Berish", callback_data="opt_order_start")],
            [InlineKeyboardButton("🔙 Ortga", callback_data="opt_back")]
        ]
        await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btn))

    elif data == "opt_poco":
        txt = (
            f"📱 <b>POCO / XIAOMI / REDMI PRO OPTIMIZATSIYA:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• Joyose va Battery Performance cheklovlarini xavfsiz o'chirish\n"
            f"• Drosselni (FPS 30-40 ga tushishini) butunlay yo'qotish\n"
            f"• Barqaror 90 / 120 FPS rejimini ochish\n"
            f"• Ekran javob tezligini (Touch Response) 480Hz ga ko'tarish\n\n"
            f"💰 Narxi: <b>Kelishilgan holda</b>"
        )
        btn = [
            [InlineKeyboardButton("🔥 VIP Buyurtma Berish", callback_data="opt_order_start")],
            [InlineKeyboardButton("🔙 Ortga", callback_data="opt_back")]
        ]
        await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btn))

    elif data == "opt_samsung":
        txt = (
            f"📱 <b>SAMSUNG GALAXY PRO OPTIMIZATSIYA:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• GOS (Game Optimizing Service) drosselini o'chirish\n"
            f"• Game Booster Plus orqali maksimal unumdorlik\n"
            f"• Qizishni kamaytirish va barqaror kadrlar chastotasi\n\n"
            f"💰 Narxi: <b>Kelishilgan holda</b>"
        )
        btn = [
            [InlineKeyboardButton("🔥 VIP Buyurtma Berish", callback_data="opt_order_start")],
            [InlineKeyboardButton("🔙 Ortga", callback_data="opt_back")]
        ]
        await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btn))

    elif data == "opt_other":
        txt = (
            f"📱 <b>UNIVERSAL ANDROID OPTIMIZATSIYA:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Realme, OnePlus, Tecno, Infinix va boshqa barcha Android telefonlar uchun kesh tozalash, "
            f"fon jarayonlarini optimallash va kiber sezgirlik sozlash."
        )
        btn = [
            [InlineKeyboardButton("🔥 VIP Buyurtma Berish", callback_data="opt_order_start")],
            [InlineKeyboardButton("🔙 Ortga", callback_data="opt_back")]
        ]
        await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btn))

    elif data == "opt_back":
        txt = (
            f"⚡ <b>PUBG MOBILE PRO OPTIMIZATSIYA XIZMATI (PULLIK VIP)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Modellardan birini tanlang yoki to'g'ridan-to'g'ri VIP buyurtma bering:"
        )
        await query.edit_message_text(txt, parse_mode="HTML", reply_markup=get_optimization_keyboard())

    elif data == "opt_order_start":
        context.user_data["state"] = "order_device"
        await query.message.reply_text(
            "📝 <b>VIP OPTIMIZATSIYA BUYURTMA BERISH</b>\n\n"
            "1-Qadam: Telefoningizning to'liq modelini yozib yuboring (Masalan: iPhone 13 Pro yoki Poco X6 Pro):",
            parse_mode="HTML"
        )

    # 4. Xalifalik (Admin Panel) Callbacks
    elif data.startswith("xalifa_"):
        if not is_admin(user.id):
            await query.answer("⛔ Ruxsat yo'q!", show_alert=True)
            return

        if data == "xalifa_stats":
            stats = get_stats()
            txt = (
                f"📊 <b>BOTNING JORIY STATISTIKASI:</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 Jami foydalanuvchilar: <b>{stats['users']} ta</b>\n"
                f"⚡ Kelib tushgan buyurtmalar: <b>{stats['orders']} ta</b>\n"
                f"💡 Qabul qilingan takliflar: <b>{stats['feedbacks']} ta</b>\n"
                f"📢 Majburiy obuna kanallari: <b>{stats['channels']} ta</b>\n"
                f"👑 Bosh Xalifa: <b>@{SUPER_ADMIN_USERNAME}</b>"
            )
            await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Xalifalikka qaytish", callback_data="xalifa_home")]]))

        elif data == "xalifa_home":
            is_super = (user.id == SUPER_ADMIN_ID)
            txt = "👑 <b>XALIFALIK BOSHQARUV MARKAZI:</b>\nQuyidagi bo'limlardan birini tanlang:"
            await query.edit_message_text(txt, parse_mode="HTML", reply_markup=get_xalifalik_keyboard(is_super))

        elif data == "xalifa_broadcast":
            context.user_data["state"] = "broadcast_text"
            txt = (
                f"📢 <b>HAMMAGA XABAR TARQATISH (BROADCAST)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Barcha bot foydalanuvchilariga yubormoqchi bo'lgan xabaringizni yozing yoki postni forward qiling:\n\n"
                f"<i>(Bekor qilish uchun /cancel deb yozing)</i>"
            )
            await query.message.reply_text(txt, parse_mode="HTML")

        elif data == "xalifa_orders":
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT id, username, device_model, fps_target, contact, created_at FROM orders ORDER BY id DESC LIMIT 5")
            orders = cur.fetchall()
            conn.close()

            if not orders:
                txt = "⚡ Hozircha yangi VIP buyurtmalar yo'q."
            else:
                txt = "⚡ <b>SO'NGGI VIP BUYURTMALAR:</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                for o in orders:
                    txt += (
                        f"🆔 #{o[0]} | @{o[1] or 'yoq'}\n"
                        f"📱 Model: <b>{o[2]}</b>\n"
                        f"🎯 Maqsad: {o[3]}\n"
                        f"📞 Aloqa: <code>{o[4]}</code>\n"
                        f"⏰ Sana: {o[5]}\n"
                        f"------------------------\n"
                    )
            await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Xalifalikka qaytish", callback_data="xalifa_home")]]))

        elif data == "xalifa_feedbacks":
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT id, username, text, created_at FROM feedbacks ORDER BY id DESC LIMIT 5")
            fbs = cur.fetchall()
            conn.close()

            if not fbs:
                txt = "💡 Hozircha takliflar mavjud emas."
            else:
                txt = "💡 <b>SO'NGGI FOYDALANUVCHI TAKLIFLARI:</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                for f in fbs:
                    txt += f"👤 @{f[1] or 'yoq'}: <i>\"{f[2]}\"</i> ({f[3]})\n\n"
            await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Xalifalikka qaytish", callback_data="xalifa_home")]]))

        elif data == "xalifa_channels":
            channels = get_sub_channels()
            txt = "📢 <b>MAJBURIY OBUNA KANALLARI:</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            if not channels:
                txt += "Hozircha majburiy kanallar o'rnatilmagan.\n"
            else:
                for c in channels:
                    txt += f"• <b>{c[1]}</b> ({c[0]}) -> {c[2]}\n"
            
            buttons = [
                [InlineKeyboardButton("➕ Kanal Qo'shish", callback_data="xalifa_add_channel")],
                [InlineKeyboardButton("🗑️ Barcha Kanallarni Tozalash", callback_data="xalifa_clear_channels")],
                [InlineKeyboardButton("🔙 Xalifalikka qaytish", callback_data="xalifa_home")],
            ]
            await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

        elif data == "xalifa_add_channel":
            context.user_data["state"] = "add_channel"
            txt = (
                "➕ <b>YANGI KANAL QO'SHISH</b>\n\n"
                "Quyidagi formatda yuboring:\n"
                "<code>@kanal_username | Kanal Sarlavhasi | https://t.me/kanal_link</code>\n\n"
                "<i>Muhim: Bot o'sha kanalda ADMIN bo'lishi shart!</i>"
            )
            await query.message.reply_text(txt, parse_mode="HTML")

        elif data == "xalifa_clear_channels":
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("DELETE FROM force_channels")
            conn.commit()
            conn.close()
            await query.answer("Kanallar ro'yxati tozalandi!", show_alert=True)
            txt = "📢 Barcha majburiy kanallar olib tashlandi."
            await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Xalifalikka qaytish", callback_data="xalifa_home")]]))

        elif data == "xalifa_manage_saids":
            if user.id != SUPER_ADMIN_ID:
                await query.answer("Faqat Bosh Xalifa Saidlarni boshqara oladi!", show_alert=True)
                return

            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT user_id, role, added_at FROM admins WHERE role = 'said'")
            saids = cur.fetchall()
            conn.close()

            txt = "👥 <b>TAYYINLANGAN SAIDLAR (ADMINLAR):</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            if not saids:
                txt += "Hozircha yordamchi Saidlar yo'q.\n"
            else:
                for s in saids:
                    txt += f"• ID: <code>{s[0]}</code> | Sana: {s[2]}\n"

            buttons = [
                [InlineKeyboardButton("➕ Yangi Said Tayinlash", callback_data="xalifa_add_said")],
                [InlineKeyboardButton("🔙 Xalifalikka qaytish", callback_data="xalifa_home")],
            ]
            await query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

        elif data == "xalifa_add_said":
            context.user_data["state"] = "add_said_id"
            await query.message.reply_text(
                "➕ <b>YANGI SAID TAYINLASH:</b>\n\n"
                "Yangi administratorning sonli Telegram ID raqamini yuboring (Masalan: 123456789):",
                parse_mode="HTML"
            )

# ==========================================================
# ⚙️ POST INIT HOOK (Set Menu Button to "ESPORT APP")
# ==========================================================
async def post_init(application):
    try:
        if MINI_APP_URL:
            # Agar foydalanuvchi mini app URL ni kiritgan bo'lsa, uni ochadi
            await application.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="ESPORT APP",
                    web_app=WebAppInfo(url=MINI_APP_URL)
                )
            )
            print("✅ Chat Menu Button 'ESPORT APP' (WebApp) sifatida o'rnatildi!", flush=True)
        else:
            # Mini app hali internetda bo'lmasa ham tugma matnini ko'rsatadi
            await application.bot.set_chat_menu_button(
                menu_button=MenuButtonDefault()
            )
            print("ℹ️ Chat Menu Button Default sifatida o'rnatildi.", flush=True)
    except Exception as e:
        print(f"Menu Button o'rnatishda xatolik: {e}", flush=True)

# ==========================================================
# 🏁 MAIN ENTRY POINT
# ==========================================================
def main():
    print("====================================================", flush=True)
    print("  🎮 PUBG Mobile Optimizer Telegram Bot ishga tushmoqda...", flush=True)
    print(f"  👑 Bosh Admin (Xalifa): {SUPER_ADMIN_ID} (@{SUPER_ADMIN_USERNAME})", flush=True)
    print("====================================================", flush=True)

    start_health_server()

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    print("✅ Bot muvaffaqiyatli ishga tushdi va xabarlarni kutmoqda!", flush=True)
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
