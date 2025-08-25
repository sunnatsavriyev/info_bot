import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncpg
from decouple import config

# ================================
# Telegram & Guruh konfiguratsiyasi
API_TOKEN = config("API_TOKEN")
GROUP_ID = int(config("GROUP_ID"))
SUPERADMINS = [int(x) for x in config("SUPERADMINS").split(",")]

# ================================
DB_USER = config("DB_USER")
DB_PASSWORD = config("DB_PASSWORD")
DB_HOST = config("DB_HOST")
DB_PORT = config("DB_PORT", cast=int)
DB_NAME = config("DB_NAME")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ---------------- Helper: Guruhga xabar yuborish ----------------
async def send_to_group(text: str):
    try:
        await bot.send_message(GROUP_ID, text)
    except Exception as e:
        for admin in SUPERADMINS:
            try:
                await bot.send_message(admin, f"❌ Guruhga yuborilmadi:\n{text}\n\nXato: {e}")
            except:
                pass

# ================================
# Boshlang'ich keyboard yangilanadi
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Xodim qo'shish")],
        [KeyboardButton(text="✏️ Xodimni o'zgartirish")],
        [KeyboardButton(text="Mening xodimlarim")]
    ],
    resize_keyboard=True
)

# Holatlar
user_states = {}
ASK_FULLNAME, ASK_PHONE, ASK_OFFICE, ASK_POSITION = range(4)

db_conn = None  # global connection

# ================================
# Bekatlar ro‘yxati (50 ta)
STATION_LIST = [
    "Beruniy","Tinchlik","Chorsu","Gʻafur Gʻulom","Alisher Navoiy","Abdulla Qodiriy",
    "Pushkin","Buyuk Ipak Yoʻli","Novza","Milliy bogʻ","Xalqlar doʻstligi","Chilonzor",
    "Mirzo Ulugʻbek","Olmazor","Doʻstlik","Mashinasozlar","Toshkent","Oybek","Kosmonavtlar",
    "Oʻzbekiston","Hamid Olimjon","Mingoʻrik","Yunus Rajabiy","Shahriston","Bodomzor","Minor",
    "Turkiston","Yunusobod","Tuzel","Yashnobod","Texnopark","Sergeli","Choshtepa","Turon",
    "Chinor","Yangiobod","Rohat","Oʻzgarish","Yangihayot","Qoʻyliq","Matonat","Qiyot","Tolariq",
    "Xonobod","Quruvchilar","Olmos","Paxtakor","Qipchoq","Amir Temur xiyoboni","Mustaqillik maydoni"
]

# ================================
# Bazani yaratish va ulanish
async def setup_db():
    global db_conn
    conn = await asyncpg.connect(
        user=DB_USER, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT, database="postgres"
    )
    exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1;", DB_NAME)
    if not exists:
        await conn.execute(f'CREATE DATABASE {DB_NAME};')
    await conn.close()

    db_conn = await asyncpg.connect(
        user=DB_USER, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT, database=DB_NAME
    )

    # Jadval yaratish
    await db_conn.execute("""
        CREATE TABLE IF NOT EXISTS stations (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE
        );
    """)
    await db_conn.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id SERIAL PRIMARY KEY,
            full_name TEXT,
            phone TEXT,
            office TEXT,
            position TEXT,
            station_id INT REFERENCES stations(id) ON DELETE CASCADE,
            photo TEXT
        );
    """)
    await db_conn.execute("""
        CREATE TABLE IF NOT EXISTS station_heads (
            id SERIAL PRIMARY KEY,
            head_telegram_id BIGINT UNIQUE,
            station_id INT REFERENCES stations(id) ON DELETE CASCADE
        );
    """)

    # 50 ta bekatni qo‘shib qo‘yish
    for st in STATION_LIST:
        await db_conn.execute(
            "INSERT INTO stations(name) VALUES($1) ON CONFLICT (name) DO NOTHING;",
            st
        )

# ================================
async def get_head_station(user_id):
    row = await db_conn.fetchrow(
        "SELECT station_id FROM station_heads WHERE head_telegram_id=$1", user_id
    )
    return row["station_id"] if row else None

# ================================
# HELP komandasi
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    if message.from_user.id in SUPERADMINS:
        text = (
            "🛠 Superadmin komandalar:\n"
            "/add_head – yangi bekat boshlig‘i qo‘shish\n"
            "/all_workers – barcha bekatlar va xodimlar ro‘yxati\n\n"
            "ℹ️ Bekat boshlig‘i komandalar:\n"
            "/start – botni boshlash\n"
        )
    else:
        text = (
            "ℹ️ Bekat boshlig‘i komandalar:\n"
            "/start – botni boshlash\n"
        )
    await message.answer(text)

# ================================
# ADMIN PANEL: boshliq qo‘shish
@dp.message(Command("add_head"))
async def add_head(message: types.Message):
    if message.from_user.id not in SUPERADMINS:
        return await message.answer("❌ Sizda ruxsat yo‘q.")

    await message.answer("👤 Yangi boshliqning Telegram ID sini yuboring:")
    user_states[message.from_user.id] = {"state": "ask_new_head_id"}


@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "ask_new_head_id")
async def ask_station(message: types.Message):
    text_id = message.text.strip()

    # 9–10 raqamdan tashqari IDlarni rad etish
    if not text_id.isdigit() or len(text_id) < 9 or len(text_id) > 10:
        return await message.answer("❌ Telegram ID noto‘g‘ri. 9–10 raqam bo‘lishi kerak.")

    new_id = int(text_id)

    # ID saqlash va keyingi bosqichga o'tish
    user_states[message.from_user.id]["new_head_id"] = new_id
    user_states[message.from_user.id]["state"] = "choose_station"

    # Bekatlar ro‘yxatini olish va inline keyboard yaratish
    stations = await db_conn.fetch("SELECT id, name FROM stations ORDER BY id")
    kb = InlineKeyboardBuilder()
    for st in stations:
        kb.button(text=st["name"], callback_data=f"setstation:{new_id}:{st['id']}")
    kb.adjust(2)

    await message.answer("🏢 Bekatni tanlang:", reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("setstation:"))
async def set_station(callback: types.CallbackQuery):
    _, new_id, station_id = callback.data.split(":")
    new_id, station_id = int(new_id), int(station_id)

    await db_conn.execute("""
        INSERT INTO station_heads(head_telegram_id, station_id)
        VALUES($1, $2)
        ON CONFLICT(head_telegram_id) DO UPDATE SET station_id=$2
    """, new_id, station_id)

    station_name = await db_conn.fetchval("SELECT name FROM stations WHERE id=$1", station_id)
    await callback.message.edit_text(f"✅ {new_id} boshliq qilib qo‘shildi.\n🏢 Bekat: {station_name}")

    # Guruhga xabar
    await send_to_group(f"👑 Yangi boshliq qo‘shildi!\n\n🆔 {new_id}\n🏢 Bekat: {station_name}")

    user_states.pop(callback.from_user.id, None)

# ================================
# START komandasi
@dp.message(Command("start"))
async def start(message: types.Message):
    if message.chat.type != "private":
        return

    if message.from_user.id in SUPERADMINS:
        return await message.answer("👑 Siz superadmin sifatida tizimdasiz.\n👉 /help buyrug‘ini bosing.")

    station_id = await get_head_station(message.from_user.id)
    if not station_id:
        return await message.answer("❌ Siz bekat boshlig‘i sifatida ro‘yxatdan o‘tmagansiz.")

    station_name = await db_conn.fetchval("SELECT name FROM stations WHERE id=$1", station_id)
    await message.answer(
        f"👋 Assalomu alaykum, {message.from_user.full_name}!\n"
        f"✅ Siz {station_name} bekati boshlig‘i sifatida ro‘yxatdan o‘tgansiz.",
        reply_markup=main_kb
    )

    # Guruhga ham log yuborish
    await send_to_group(
        f"ℹ️ {message.from_user.full_name} (ID: {message.from_user.id}) "
        f"`/start` bosdi.\n🏢 Bekat: {station_name}"
    )

# ================================
# Bekat boshlig‘i – o‘z xodimlarini ko‘rish
@dp.message(F.text == "Mening xodimlarim")
async def my_workers(message: types.Message):
    station_id = await get_head_station(message.from_user.id)
    if not station_id:
        return await message.answer("❌ Siz boshliq emassiz.")

    workers = await db_conn.fetch("SELECT * FROM workers WHERE station_id=$1", station_id)
    station_name = await db_conn.fetchval("SELECT name FROM stations WHERE id=$1", station_id)

    if not workers:
        return await message.answer("❌ Sizda hozircha xodimlar yo‘q.")

    await message.answer(f"🏢 Bekat: {station_name}\n📝 Xodimlar ro‘yxati:")
    for w in workers:
        caption = (f"👤 {w['full_name']}\n"
                   f"🏢 {w['office']}\n"
                   f"💼 {w['position']}")
        if w['photo']:
            await message.answer_photo(photo=w['photo'], caption=caption)
        else:
            await message.answer(caption)

# ================================
# Superadmin – barcha bekatlar va xodimlar
@dp.message(Command("all_workers"))
async def all_workers(message: types.Message):
    if message.from_user.id not in SUPERADMINS:
        return await message.answer("❌ Siz superadmin emassiz.")

    stations = await db_conn.fetch("SELECT id, name FROM stations ORDER BY id")
    if not stations:
        return await message.answer("❌ Hozircha hech qanday bekat yo‘q.")

    await message.answer("📋 Barcha bekatlar va xodimlar:")
    for st in stations:
        workers = await db_conn.fetch("SELECT * FROM workers WHERE station_id=$1", st["id"])
        if not workers:
            continue
        await message.answer(f"🏢 {st['name']}:")
        for w in workers:
            caption = (f"👤 {w['full_name']}\n"
                       f"🏢 {w['office']}\n"
                       f"💼 {w['position']}")
            if w['photo']:
                await message.answer_photo(photo=w['photo'], caption=caption)
            else:
                await message.answer(caption)

# ================================
# Worker qo‘shish (telefon olinmaydi, rasm tekshiriladi)
@dp.message(F.text == "➕ Xodim qo'shish")
async def add_worker(message: types.Message):
    user_states[message.from_user.id] = {'state': ASK_FULLNAME, 'mode': 'new'}
    await message.answer("👤 Yangi xodimning F.I.O sini kiriting:")

@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == ASK_FULLNAME)
async def ask_position(message: types.Message):
    user_states[message.from_user.id]["full_name"] = message.text
    user_states[message.from_user.id]["state"] = ASK_POSITION
    await message.answer("💼 Lavozimini kiriting:")

@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == ASK_POSITION)
async def ask_photo(message: types.Message):
    user_states[message.from_user.id]["position"] = message.text
    user_states[message.from_user.id]["state"] = "ASK_PHOTO"
    await message.answer("🖼️ Xodimning rasm linkini yuboring yoki rasmini yuboring (jpg, png, webp):")

@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "ASK_PHOTO")
async def save_worker(message: types.Message):
    # Rasm link yoki fayl tekshirish
    if message.photo:
        photo = message.photo[-1].file_id
    elif message.text and (message.text.startswith("http://") or message.text.startswith("https://")):
        photo = message.text
    else:
        return await message.answer("❌ Faqat rasm yuborilishi yoki rasm linki bo‘lishi kerak. Qayta yuboring:")

    user_states[message.from_user.id]["photo"] = photo

    station_id = await get_head_station(message.from_user.id)
    if not station_id:
        return await message.answer("❌ Siz boshliq emassiz.")

    station_name = await db_conn.fetchval("SELECT name FROM stations WHERE id=$1", station_id)

    await db_conn.execute("""
        INSERT INTO workers(full_name, phone, office, position, station_id, photo)
        VALUES($1,$2,$3,$4,$5,$6)
    """,
        user_states[message.from_user.id]["full_name"],
        None,  # telefon olib tashlandi
        station_name,
        user_states[message.from_user.id]["position"],
        station_id,
        photo
    )

    text = (
        f"✅ Xodim qo‘shildi!\n"
        f"🏢 Bekat: {station_name}\n"
        f"👤 {user_states[message.from_user.id]['full_name']}\n"
        f"💼 {user_states[message.from_user.id]['position']}"
    )
    await message.answer(text, reply_markup=main_kb)
    await send_to_group(f"➕ Yangi xodim qo‘shildi!\n\n{text}")

    user_states.pop(message.from_user.id, None)

# ================================
# Worker tahrir – bir nechta maydonni ketma-ket
@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "edit_choice")
async def edit_field(message: types.Message):
    choice = message.text
    worker_id = user_states[message.from_user.id]["worker_id"]

    if choice in ["📞 Telefon", "💼 Lavozim"]:
        field = "phone" if choice == "📞 Telefon" else "position"
        user_states[message.from_user.id]["current_field"] = field
        user_states[message.from_user.id]["state"] = "edit_field_value"
        return await message.answer(f"🔄 Yangi {choice} kiriting:")

    if choice == "🏢 Bekatni o‘zgartirish":
        stations = await db_conn.fetch("SELECT id, name FROM stations ORDER BY id")
        kb = InlineKeyboardBuilder()
        for st in stations:
            kb.button(text=st["name"], callback_data=f"changestation:{worker_id}:{st['id']}")
        kb.adjust(2)
        return await message.answer("🏢 Yangi bekatni tanlang:", reply_markup=kb.as_markup())

    if choice == "❌ Bekor qilish":
        user_states.pop(message.from_user.id, None)
        return await message.answer("Bekor qilindi.", reply_markup=main_kb)

@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "edit_field_value")
async def save_field_value(message: types.Message):
    field = user_states[message.from_user.id]["current_field"]
    worker_id = user_states[message.from_user.id]["worker_id"]

    await db_conn.execute(f"UPDATE workers SET {field}=$1 WHERE id=$2", message.text, worker_id)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Ha"), KeyboardButton(text="Yo‘q")]],
        resize_keyboard=True
    )
    user_states[message.from_user.id]["state"] = "edit_another"
    await message.answer(f"✅ {field.capitalize()} yangilandi.\nYana boshqa maydonni o‘zgartirasizmi?", reply_markup=kb)

@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "edit_another")
async def edit_another_choice(message: types.Message):
    if message.text == "Ha":
        user_states[message.from_user.id]["state"] = "edit_choice"
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📞 Telefon"), KeyboardButton(text="💼 Lavozim")],
                [KeyboardButton(text="🏢 Bekatni o‘zgartirish")],
                [KeyboardButton(text="❌ Bekor qilish")]
            ],
            resize_keyboard=True
        )
        await message.answer("Qaysi maydonni o‘zgartirmoqchisiz?", reply_markup=kb)
    else:
        user_states.pop(message.from_user.id, None)
        await message.answer("✅ Tahrir yakunlandi.", reply_markup=main_kb)

# ================================
async def main(): 
    await setup_db() 
    await dp.start_polling(bot)
    
if __name__ == "__main__": 
    asyncio.run(main())
