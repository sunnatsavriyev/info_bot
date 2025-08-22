import asyncio
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import asyncpg
from decouple import config

# ================================
# Telegram & Guruh konfiguratsiyasi
API_TOKEN = config("API_TOKEN")
GROUP_ID = int(config("GROUP_ID"))
# ================================

DB_USER = config("DB_USER")
DB_PASSWORD = config("DB_PASSWORD")
DB_HOST = config("DB_HOST")
DB_PORT = config("DB_PORT", cast=int)
DB_NAME = config("DB_NAME")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Boshlang'ich keyboard (faqat private chat uchun)
main_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Ma'lumot qo'shish / o'zgartirish")]],
    resize_keyboard=True
)

# Ha/Yo‘q keyboard (faqat private chat uchun)
yesno_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Ha"), KeyboardButton(text="Yo‘q")]],
    resize_keyboard=True
)

# Holatlar
user_states = {}
ASK_FULLNAME, ASK_PHONE, ASK_OFFICE, ASK_POSITION, ASK_EDIT_FIELD, ASK_CONTINUE = range(6)

db_conn = None  # global connection

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
    await db_conn.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            first_name TEXT,
            last_name TEXT,
            middle_name TEXT,
            phone TEXT,
            office TEXT,
            position TEXT
        );
    """)

# ================================
async def send_to_group(message_text):
    await bot.send_message(GROUP_ID, message_text)

# Barcha foydalanuvchilarga yuborish
async def notify_all_users(message_text: str):
    users = await db_conn.fetch("SELECT telegram_id FROM workers")
    for u in users:
        try:
            await bot.send_message(u["telegram_id"], message_text)
        except Exception as e:
            print(f"❌ {u['telegram_id']} ga yuborilmadi: {e}")

# ================================
# Guruhdagi komandalarni bloklash
@dp.message(lambda m: m.chat.id == GROUP_ID)
async def block_group_cmds(message: types.Message):
    if message.text.startswith("/") or message.text in ["Ma'lumot qo'shish / o'zgartirish", "Ha", "Yo‘q"]:
        return  # guruhda buyruq yoki tugmalarni e’tiborga olma

# ================================
@dp.message(F.text == "/start")
async def start(message: types.Message):
    if message.chat.type != "private":
        return  # faqat private da ishlasin

    user = await db_conn.fetchrow("SELECT * FROM workers WHERE telegram_id=$1", message.from_user.id)
    if user:
        text = (
            f"📝 Sizning ma'lumotlaringiz:\n"
            f"Ism: {user['first_name']} {user['last_name']} {user['middle_name']}\n"
            f"Telefon: {user['phone']}\n"
            f"Ish joyi/xona: {user['office']}\n"
            f"Lavozim: {user['position']}\n\n"
            f"✏️ Ma'lumotni o'zgartirish uchun tugmani bosing."
        )
        await message.answer(text, reply_markup=main_kb)
    else:
        # yangi foydalanuvchi qo‘shish
        user_states[message.from_user.id] = {'state': ASK_FULLNAME, 'mode': 'new'}
        await message.answer("👤 To‘liq ism familya otasining ismini kiriting:")

@dp.message(F.text == "Ma'lumot qo'shish / o'zgartirish")
async def edit_data(message: types.Message):
    if message.chat.type != "private":
        return

    user = await db_conn.fetchrow("SELECT * FROM workers WHERE telegram_id=$1", message.from_user.id)
    if not user:
        user_states[message.from_user.id] = {'state': ASK_FULLNAME, 'mode': 'new'}
        await message.answer("👤 To‘liq ism familya otasining ismini kiriting:")
    else:
        text = (
            f"📝 Sizning hozirgi ma'lumotlaringiz:\n\n"
            f"1️⃣ F.I.O: {user['first_name']} {user['last_name']} {user['middle_name']}\n"
            f"2️⃣ Telefon: {user['phone']}\n"
            f"3️⃣ Ish joyi/xona: {user['office']}\n"
            f"4️⃣ Lavozim: {user['position']}\n\n"
            f"Qaysi raqamdagi maydonni o‘zgartirmoqchisiz? (1–4):"
        )
        user_states[message.from_user.id] = {'state': ASK_EDIT_FIELD, 'mode': 'edit'}
        await message.answer(text)

# ================================
@dp.message(lambda m: m.from_user.id in user_states)
async def process_state(message: types.Message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
    state = user_states[user_id]['state']
    mode = user_states[user_id]['mode']

    # F.I.O
    if state == ASK_FULLNAME:
        parts = message.text.split()
        if len(parts) < 3:
            return await message.answer("❌ To‘liq ism familya otasining ismini kiriting (kamida 3 ta so‘z bo‘lsin)!")
        user_states[user_id]['first_name'] = parts[0]
        user_states[user_id]['last_name'] = parts[1]
        user_states[user_id]['middle_name'] = " ".join(parts[2:])
        if mode == 'new':
            user_states[user_id]['state'] = ASK_PHONE
            return await message.answer("📞 Telefon raqamingizni kiriting:")
        else:
            user_states[user_id]['state'] = ASK_CONTINUE
            return await message.answer("🔄 Yana o‘zgartirasizmi?", reply_markup=yesno_kb)

    # Telefon
    if state == ASK_PHONE:
        phone = message.text.strip()
        if not re.fullmatch(r'^\+?\d{9,13}$', phone):
            return await message.answer("❌ Telefon raqam noto‘g‘ri formatda.")
        user_states[user_id]['phone'] = phone
        if mode == 'new':
            user_states[user_id]['state'] = ASK_OFFICE
            return await message.answer("🏢 Ish joyi va xona raqamini kiriting:")
        else:
            user_states[user_id]['state'] = ASK_CONTINUE
            return await message.answer("🔄 Yana o‘zgartirasizmi?", reply_markup=yesno_kb)

    # Office
    if state == ASK_OFFICE:
        user_states[user_id]['office'] = message.text
        if mode == 'new':
            user_states[user_id]['state'] = ASK_POSITION
            return await message.answer("💼 Lavozimingizni kiriting:")
        else:
            user_states[user_id]['state'] = ASK_CONTINUE
            return await message.answer("🔄 Yana o‘zgartirasizmi?", reply_markup=yesno_kb)

    # Position
    if state == ASK_POSITION:
        user_states[user_id]['position'] = message.text
        if mode == 'new':
            await save_user(user_id)
            await message.answer("✅ Ma'lumotlaringiz saqlandi", reply_markup=main_kb)
            user_states.pop(user_id)
        else:
            user_states[user_id]['state'] = ASK_CONTINUE
            return await message.answer("🔄 Yana o‘zgartirasizmi?", reply_markup=yesno_kb)

    # 1–4 tanlash
    if state == ASK_EDIT_FIELD:
        choice = message.text.strip()
        if choice not in ["1", "2", "3", "4"]:
            return await message.answer("❌ 1–4 oralig‘ida raqam tanlang.")
        if choice == "1":
            user_states[user_id]['state'] = ASK_FULLNAME
            return await message.answer("✏️ Yangi F.I.O ni kiriting:")
        if choice == "2":
            user_states[user_id]['state'] = ASK_PHONE
            return await message.answer("✏️ Yangi telefon raqamni kiriting:")
        if choice == "3":
            user_states[user_id]['state'] = ASK_OFFICE
            return await message.answer("✏️ Yangi ish joyi/xona kiriting:")
        if choice == "4":
            user_states[user_id]['state'] = ASK_POSITION
            return await message.answer("✏️ Yangi lavozim kiriting:")

    # Ha/Yo‘q
    if state == ASK_CONTINUE:
        if message.text == "Ha":
            user_states[user_id]['state'] = ASK_EDIT_FIELD
            return await message.answer("Qaysi maydonni o‘zgartirasiz? (1–4):", reply_markup=ReplyKeyboardRemove())
        else:
            await save_user(user_id)
            await message.answer("✅ Ma'lumotlaringiz saqlandi", reply_markup=main_kb)
            user_states.pop(user_id)

# ================================
async def save_user(user_id):
    existing = await db_conn.fetchrow("SELECT * FROM workers WHERE telegram_id=$1", user_id)
    if existing:
        msg = "✏️ Foydalanuvchi ma'lumotlari yangilandi."
    else:
        msg = "🆕 Yangi foydalanuvchi qo‘shildi."

    await db_conn.execute("""
        INSERT INTO workers (telegram_id, first_name, last_name, middle_name, phone, office, position)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        ON CONFLICT (telegram_id) DO UPDATE SET
            first_name=EXCLUDED.first_name,
            last_name=EXCLUDED.last_name,
            middle_name=EXCLUDED.middle_name,
            phone=EXCLUDED.phone,
            office=EXCLUDED.office,
            position=EXCLUDED.position
    """,
    user_id,
    user_states[user_id].get('first_name'),
    user_states[user_id].get('last_name'),
    user_states[user_id].get('middle_name'),
    user_states[user_id].get('phone'),
    user_states[user_id].get('office'),
    user_states[user_id].get('position'))

    text = (
        f"{msg}\n\n"
        f"👤 {user_states[user_id].get('first_name')} {user_states[user_id].get('last_name')} {user_states[user_id].get('middle_name')}\n"
        f"📞 {user_states[user_id].get('phone')}\n"
        f"🏢 {user_states[user_id].get('office')}\n"
        f"💼 {user_states[user_id].get('position')}"
    )

    # Guruhga yuborish
    await send_to_group(text)

    # Barcha foydalanuvchilarga yuborish
    await notify_all_users(text)

# ================================
async def main():
    await setup_db()
    await send_to_group("🤖 Bot ishga tushdi ✅")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
