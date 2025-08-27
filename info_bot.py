import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncpg
from decouple import config
# ================================
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
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
            full_name TEXT NOT NULL,
            tabel VARCHAR(10) NOT NULL,
            position TEXT NOT NULL,
            smena INT NOT NULL,
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
# ================================
# HELP komandasi
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    if message.from_user.id in SUPERADMINS:
        text = (
            "🛠 Superadmin komandalar:\n"
            "/add_head – yangi bekat boshlig‘i qo‘shish\n"
            "/edit_head – mavjud boshliqni tahrirlash\n"
            "/delete_head – boshliqni o‘chirish\n"
            "/all_workers – bekat bo‘yicha xodimlar ro‘yxati\n\n"
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
    if not text_id.isdigit() or len(text_id) < 9 or len(text_id) > 10:
        return await message.answer("❌ Telegram ID noto‘g‘ri. 9–10 raqam bo‘lishi kerak.")

    new_id = int(text_id)
    user_states[message.from_user.id]["new_head_id"] = new_id
    user_states[message.from_user.id]["state"] = "choose_station"

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
    await send_to_group(f"👑 Yangi boshliq qo‘shildi!\n\n🆔 {new_id}\n🏢 Bekat: {station_name}")
    user_states.pop(callback.from_user.id, None)



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

    # Admin uchun xabar
    await callback.message.edit_text(
        f"✅ {new_id} boshliq qilib qo‘shildi.\n🏢 Bekat: {station_name}"
    )

    # Guruhga xabar
    await send_to_group(
        f"👑 Yangi boshliq qo‘shildi!✅\n\n🆔 {new_id}\n🏢 Bekat: {station_name}"
    )

    # Yangi boshliqning o‘ziga xabar
    try:
        await bot.send_message(
            new_id,
            f"🎉 Tabriklaymiz!\nSiz {station_name} bekatining boshlig‘i qilib tayinlandingiz."
        )
    except Exception as e:
        # Agar foydalanuvchi botni start qilmagan bo‘lsa xato chiqadi
        print(f"Xabar yuborilmadi: {e}")

    user_states.pop(callback.from_user.id, None)



# ================================
# EDIT HEAD
@dp.message(Command("edit_head"))
async def edit_head(message: types.Message):
    if message.from_user.id not in SUPERADMINS:
        return await message.answer("❌ Sizda ruxsat yo‘q.")
    
    stations = await db_conn.fetch("SELECT id, name FROM stations ORDER BY id")
    kb = InlineKeyboardBuilder()
    for st in stations:
        kb.button(text=st["name"], callback_data=f"edith_head_station:{st['id']}")
    kb.adjust(2)
    await message.answer("✏️ Qaysi bekat boshliqini tahrirlashni xohlaysiz?", reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("edith_head_station:"))
async def edith_head_station(callback: types.CallbackQuery):
    _, station_id = callback.data.split(":")
    heads = await db_conn.fetch("SELECT head_telegram_id FROM station_heads WHERE station_id=$1", int(station_id))
    if not heads:
        return await callback.message.edit_text("❌ Ushbu bekatda boshliq yo‘q.")
    
    kb = InlineKeyboardBuilder()
    for h in heads:
        kb.button(text=str(h["head_telegram_id"]), callback_data=f"edit_head_id:{h['head_telegram_id']}")
    kb.adjust(2)
    await callback.message.edit_text("✏️ Tahrirlash uchun boshliqni tanlang:", reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("edit_head_id:"))
async def edit_head_id(callback: types.CallbackQuery):
    _, head_id = callback.data.split(":")
    user_states[callback.from_user.id] = {"state": "edit_head_choose_station", "edit_head_id": int(head_id)}
    stations = await db_conn.fetch("SELECT id, name FROM stations ORDER BY id")
    kb = InlineKeyboardBuilder()
    for st in stations:
        kb.button(text=st["name"], callback_data=f"edit_head_setstation:{head_id}:{st['id']}")
    kb.adjust(2)
    await callback.message.edit_text("🏢 Yangi bekatni tanlang:", reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("edit_head_setstation:"))
async def edit_head_setstation(callback: types.CallbackQuery):
    _, head_id, new_station_id = callback.data.split(":")
    head_id, new_station_id = int(head_id), int(new_station_id)

    await db_conn.execute("UPDATE station_heads SET station_id=$1 WHERE head_telegram_id=$2", new_station_id, head_id)
    station_name = await db_conn.fetchval("SELECT name FROM stations WHERE id=$1", new_station_id)

    # Admin uchun xabar
    await callback.message.edit_text(f"✅ {head_id} boshliq yangilandi.\n🏢 Yangi bekat: {station_name}")

    # Guruhga xabar
    await send_to_group(f"✏️ Boshliq yangilandi!\n\n🆔 {head_id}\n🏢 Yangi bekat: {station_name}")

    # Boshliqning o‘ziga xabar
    try:
        await bot.send_message(
            head_id,
            f"ℹ️ Sizning boshliq maqomingiz yangilandi.\n🏢 Endi siz {station_name} bekatiga boshliq qilib tayinlandingiz."
        )
    except Exception as e:
        print(f"Xabar yuborilmadi: {e}")


# ================================
# DELETE HEAD
@dp.message(Command("delete_head"))
async def delete_head(message: types.Message):
    if message.from_user.id not in SUPERADMINS:
        return await message.answer("❌ Sizda ruxsat yo‘q.")
    
    heads = await db_conn.fetch("SELECT head_telegram_id, station_id FROM station_heads")
    if not heads:
        return await message.answer("❌ Hozircha hech qanday boshliq yo‘q.")
    
    kb = InlineKeyboardBuilder()
    for h in heads:
        station_name = await db_conn.fetchval("SELECT name FROM stations WHERE id=$1", h["station_id"])
        kb.button(text=f"{h['head_telegram_id']} ({station_name})", callback_data=f"delete_head_id:{h['head_telegram_id']}")
    kb.adjust(2)
    await message.answer("🗑 O‘chirish uchun boshliqni tanlang:", reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("delete_head_id:"))
async def delete_head_id(callback: types.CallbackQuery):
    _, head_id = callback.data.split(":")
    head_id = int(head_id)

    # O‘chirishdan oldin bekatni olish
    station_name = await db_conn.fetchval("SELECT name FROM stations WHERE head_telegram_id=$1", head_id)

    await db_conn.execute("DELETE FROM station_heads WHERE head_telegram_id=$1", head_id)

    # Admin uchun xabar
    await callback.message.edit_text(f"✅ {head_id} boshliq o‘chirildi.\n🏢 Bekat: {station_name}")

    # Guruhga xabar
    await send_to_group(f"🗑 Boshliq o‘chirildi!\n\n🆔 {head_id}\n🏢 Bekat: {station_name}")

    # Boshliqning o‘ziga xabar
    try:
        await bot.send_message(
            head_id,
            f"⚠️ Siz {station_name} bekati boshlig‘i lavozimidan ozod qilindingiz."
        )
    except Exception as e:
        print(f"Xabar yuborilmadi: {e}")






# ========== STATE ==========
class WorkerSelect(StatesGroup):
    waiting_for_number = State()


# ================================
# ALL WORKERS
@dp.message(Command("all_workers"))
async def all_workers(message: types.Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        return await message.answer("❌ Sizda ruxsat yo‘q.")

    stations = await db_conn.fetch("SELECT id, name FROM stations ORDER BY id")
    kb = InlineKeyboardBuilder()
    for st in stations:
        kb.button(text=st["name"], callback_data=f"all_workers_station:{st['id']}")
    kb.adjust(2)
    await message.answer("🏢 Qaysi bekat xodimlarini ko‘rmoqchisiz?", reply_markup=kb.as_markup())


# ================================
# WORKERS LIST
@dp.callback_query(F.data.startswith("all_workers_station:"))
async def all_workers_station(callback: types.CallbackQuery, state: FSMContext):
    _, station_id = callback.data.split(":")
    station_id = int(station_id)

    # Bekat nomini olish
    station_name = await db_conn.fetchval("SELECT name FROM stations WHERE id=$1", station_id)

    # Xodimlarni olish
    workers = await db_conn.fetch(
        "SELECT id, full_name, tabel, position, smena FROM workers WHERE station_id=$1 ORDER BY id", 
        station_id
    )

    if not workers:
        return await callback.message.edit_text(f"❌ {station_name} bekatida xodim yo‘q.")

    # Raqamlar bilan chiqarish (tugmasiz)
    text = f"🏢 Bekat: {station_name}\n📝 Xodimlar ro‘yxati:\n\n"
    for idx, w in enumerate(workers, start=1):
        text += f"{idx}. {w['full_name']} — {w['tabel']} — {w['position']} — {w['smena']}\n"

    text += "\n✍️ Kerakli xodim raqamini yozing (masalan: 1)"

    await callback.message.edit_text(text)

    # STATEga saqlash
    await state.set_state(WorkerSelect.waiting_for_number)
    await state.update_data(workers=[dict(w) for w in workers])


# ================================
# WORKER DETAIL (raqam yozilganda)
@dp.message(WorkerSelect.waiting_for_number)
async def worker_detail(message: types.Message, state: FSMContext):
    data = await state.get_data()
    workers = data.get("workers", [])

    if not message.text.isdigit():
        return await message.answer("❌ Iltimos, faqat raqam yozing (masalan: 1).")

    idx = int(message.text)
    if idx < 1 or idx > len(workers):
        return await message.answer("❌ Noto‘g‘ri raqam, ro‘yxatdan tanlang.")

    worker = workers[idx - 1]

    # Batafsil ma'lumot olish
    w = await db_conn.fetchrow(
        "SELECT w.full_name, w.tabel, w.position, w.smena, w.photo, s.name AS station_name "
        "FROM workers w "
        "JOIN stations s ON w.station_id = s.id "
        "WHERE w.id=$1", 
        worker["id"]
    )

    caption = (
        f"👤 {w['full_name']}\n"
        f"🔢 Tabel: {w['tabel']}\n"
        f"💼 Lavozim: {w['position']}\n"
        f"🕒 Smena: {w['smena']}\n"
        f"🏢 Bekat: {w['station_name']}"
    )

    if w['photo']:
        await message.answer_photo(photo=w['photo'], caption=caption)
    else:
        await message.answer(caption)

    # State tugatish
    await state.clear()


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

    workers = await db_conn.fetch("SELECT * FROM workers WHERE station_id=$1 ORDER BY id", station_id)
    station_name = await db_conn.fetchval("SELECT name FROM stations WHERE id=$1", station_id)

    if not workers:
        return await message.answer("❌ Sizda hozircha xodimlar yo‘q.")

    await message.answer(f"🏢 Bekat: {station_name}\n📝 Xodimlar ro‘yxati:")

    for idx, w in enumerate(workers, start=1):
        caption = (f"{idx}. 👤 {w['full_name']}\n"
                   f"   🔢 Tabel: {w['tabel']}\n"
                   f"   💼 Lavozim: {w['position']}\n"
                   f"   🕒 Smena: {w['smena']}")
        
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
        workers = await db_conn.fetch("SELECT * FROM workers WHERE station_id=$1 ORDER BY id", st["id"])
        if not workers:
            continue

        text = [f"🏢 {st['name']}:"]
        for idx, w in enumerate(workers, start=1):
            caption = (f"{idx}. 👤 {w['full_name']}\n"
                       f"   🔢 Tabel: {w['tabel']}\n"
                       f"   💼 Lavozim: {w['position']}\n"
                       f"   🕒 Smena: {w['smena']}")
            
            if w['photo']:
                await message.answer_photo(photo=w['photo'], caption=caption)
            else:
                text.append(caption)

        # Agar ba'zi xodimlarda rasm bo‘lmasa, matnni jo‘natamiz
        if len(text) > 1:
            await message.answer("\n".join(text))



# ================================
# Worker qo‘shish (telefon olinmaydi, rasm tekshiriladi)
@dp.message(F.text == "➕ Xodim qo'shish")
async def add_worker(message: types.Message):
    user_states[message.from_user.id] = {'state': "ASK_FULLNAME", 'mode': 'new'}
    await message.answer("👤 Yangi xodimning F.I.O sini kiriting:")


# F.I.O dan keyin tabel raqami
@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "ASK_FULLNAME")
async def ask_tabel(message: types.Message):
    user_states[message.from_user.id]["full_name"] = message.text
    user_states[message.from_user.id]["state"] = "ASK_TABEL"
    await message.answer("🔢 Tabel raqamini kiriting (masalan: 01000):")


@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "ASK_TABEL")
async def ask_position(message: types.Message):
    tabel = message.text.strip()
    if not (tabel.isdigit() and len(tabel) == 5):
        return await message.answer("❌ Tabel raqam faqat 5 xonali raqam bo‘lishi kerak. Qayta kiriting:")

    user_states[message.from_user.id]["tabel"] = tabel
    user_states[message.from_user.id]["state"] = "ASK_POSITION"

    # Lavozim variantlari
    positions = ["ДСЦП", "ДСП", "ДСПО", "ДСПЕ", "ОПЕРАТОР", "КАТТА ОПЕРАТОР", "УПП", "БЕКАТ БОШЛИҒИ"]
    kb = InlineKeyboardBuilder()
    for pos in positions:
        kb.button(text=pos, callback_data=f"choose_position:{pos}")
    kb.adjust(2)
    await message.answer("💼 Lavozimni tanlang:", reply_markup=kb.as_markup())


# Inline tanlash - lavozim
@dp.callback_query(F.data.startswith("choose_position:"))
async def choose_position(callback: types.CallbackQuery):
    position = callback.data.split(":")[1]
    user_states[callback.from_user.id]["position"] = position
    user_states[callback.from_user.id]["state"] = "ASK_SMENA"

    kb = InlineKeyboardBuilder()
    for smena in range(1, 5):
        kb.button(text=f"{smena}-smena", callback_data=f"choose_smena:{smena}")
    kb.adjust(2)

    await callback.message.edit_text(f"✅ Lavozim: {position}\n\n🕒 Endi smenasini tanlang:", reply_markup=kb.as_markup())


# Inline tanlash - smena
@dp.callback_query(F.data.startswith("choose_smena:"))
async def choose_smena(callback: types.CallbackQuery):
    smena = callback.data.split(":")[1]
    user_states[callback.from_user.id]["smena"] = smena
    user_states[callback.from_user.id]["state"] = "ASK_PHOTO"

    await callback.message.edit_text(f"✅ Smena: {smena}\n\n🖼️ Xodimning rasm linkini yuboring yoki rasmini yuboring (jpg, png, webp):")


# Rasm qabul qilish va saqlash
@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "ASK_PHOTO")
async def save_worker(message: types.Message):
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
        INSERT INTO workers(full_name, tabel, position, smena, station_id, photo)
        VALUES($1,$2,$3,$4,$5,$6)
    """,
        user_states[message.from_user.id]["full_name"],
        user_states[message.from_user.id]["tabel"],
        user_states[message.from_user.id]["position"],
        int(user_states[message.from_user.id]["smena"]),
        station_id,
        photo
    )

    text = (
        f"✅ Xodim qo‘shildi!\n"
        f"🏢 Bekat: {station_name}\n"
        f"👤 {user_states[message.from_user.id]['full_name']}\n"
        f"🔢 Tabel: {user_states[message.from_user.id]['tabel']}\n"
        f"💼 Lavozim: {user_states[message.from_user.id]['position']}\n"
        f"🕒 Smena: {user_states[message.from_user.id]['smena']}"
    )
    await message.answer(text, reply_markup=main_kb)
    await send_to_group(f"➕ Yangi xodim qo‘shildi!\n\n{text}")

    user_states.pop(message.from_user.id, None)


# ================================

# Bekat boshlig‘i – xodimni o‘zgartirish
@dp.message(F.text == "✏️ Xodimni o'zgartirish")
async def choose_worker(message: types.Message):
    station_id = await get_head_station(message.from_user.id)
    if not station_id:
        return await message.answer("❌ Siz boshliq emassiz.")

    workers = await db_conn.fetch("SELECT id, full_name FROM workers WHERE station_id=$1", station_id)
    if not workers:
        return await message.answer("❌ Sizda hozircha xodimlar yo‘q.")

    text = "👥 Xodimlar ro‘yxati:\n\n"
    for i, w in enumerate(workers, start=1):
        text += f"{i}. {w['full_name']}\n"

    user_states[message.from_user.id] = {"state": "choose_worker", "workers": workers}
    await message.answer(text + "\n✏️ Qaysi xodimni tahrir qilmoqchisiz? Raqam yuboring:")


# ================================
# Xodim tanlash
@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "choose_worker")
async def show_worker_info(message: types.Message):
    state = user_states.get(message.from_user.id)
    workers = state["workers"]

    if not message.text.isdigit() or not (1 <= int(message.text) <= len(workers)):
        return await message.answer("❌ Noto‘g‘ri raqam. Qayta kiriting:")

    idx = int(message.text) - 1
    worker = workers[idx]
    worker_id = worker["id"]

    await show_worker_fields(message.from_user.id, message, worker_id)


# ================================
# Umumiy funksiya: xodim maydonlarini chiqarish
async def show_worker_fields(user_id, message_or_callback, worker_id):
    db_worker = await db_conn.fetchrow("SELECT * FROM workers WHERE id=$1", worker_id)
    station_name = await db_conn.fetchval("SELECT name FROM stations WHERE id=$1", db_worker["station_id"])

    text = (
        f"1. 👤 F.I.O: {db_worker['full_name']}\n"
        f"2. 🔢 Tabel: {db_worker['tabel']}\n"
        f"3. 💼 Lavozim: {db_worker['position']}\n"
        f"4. 🕒 Smena: {db_worker['smena']}\n"
        f"5. 🏢 Bekat: {station_name}\n"
        f"6. 🖼 Rasm\n"
    )

    user_states[user_id] = {"state": "edit_worker_field", "worker_id": worker_id}

    # Agar rasm bor bo‘lsa, uni chiqaramiz
    if db_worker["photo"]:
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer_photo(
                photo=db_worker["photo"], 
                caption=text + "\n✏️ Qaysi maydonni o‘zgartirasiz? Raqam yuboring:"
            )
        else:
            await message_or_callback.message.answer_photo(
                photo=db_worker["photo"], 
                caption=text + "\n✏️ Qaysi maydonni o‘zgartirasiz? Raqam yuboring:"
            )
    else:
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(text + "\n✏️ Qaysi maydonni o‘zgartirasiz? Raqam yuboring:")
        else:
            await message_or_callback.message.answer(text + "\n✏️ Qaysi maydonni o‘zgartirasiz? Raqam yuboring:")


# ================================
# Maydonni tanlash va o‘zgartirish
@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "edit_worker_field")
async def edit_worker_field(message: types.Message):
    state = user_states[message.from_user.id]
    worker_id = state["worker_id"]

    if not message.text.isdigit() or not (1 <= int(message.text) <= 6):
        return await message.answer("❌ Noto‘g‘ri raqam. Qayta kiriting:")

    choice = int(message.text)

    if choice == 1:  # FIO
        state["state"] = "edit_fullname"
        return await message.answer("✏️ Yangi F.I.O ni kiriting:")

    elif choice == 2:  # Tabel
        state["state"] = "edit_tabel"
        return await message.answer("✏️ Yangi tabel raqam (5 xonali) kiriting:")

    elif choice == 3:  # Lavozim
        positions = ["ДСЦП", "ДСП", "ДСПО", "ДСПЕ", "ОПЕРАТОР", "КАТТА ОПЕРАТОР", "УПП"]
        kb = InlineKeyboardBuilder()
        for pos in positions:
            kb.button(text=pos, callback_data=f"edit_position:{worker_id}:{pos}")
        kb.adjust(2)
        return await message.answer("💼 Yangi lavozimni tanlang:", reply_markup=kb.as_markup())

    elif choice == 4:  # Smena
        kb = InlineKeyboardBuilder()
        for smena in range(1, 5):
            kb.button(text=f"{smena}-smena", callback_data=f"edit_smena:{worker_id}:{smena}")
        kb.adjust(2)
        return await message.answer("🕒 Yangi smenani tanlang:", reply_markup=kb.as_markup())

    elif choice == 5:  # Bekat
        stations = await db_conn.fetch("SELECT id, name FROM stations ORDER BY id")
        kb = InlineKeyboardBuilder()
        for st in stations:
            kb.button(text=st["name"], callback_data=f"changestation:{worker_id}:{st['id']}")  
        kb.adjust(2)
        return await message.answer("🏢 Yangi bekatni tanlang:", reply_markup=kb.as_markup())

    elif choice == 6:  # Rasm
        state["state"] = "edit_photo"
        return await message.answer("🖼 Yangi rasmni yuboring (jpg/png):")


# ================================
# Inline callback – Lavozimni yangilash
@dp.callback_query(F.data.startswith("edit_position"))
async def process_edit_position(call: types.CallbackQuery):
    _, worker_id, pos = call.data.split(":")
    await db_conn.execute("UPDATE workers SET position=$1 WHERE id=$2", pos, int(worker_id))
    await call.answer("✅ Lavozim yangilandi")
    await ask_edit_more(call.from_user.id, call, int(worker_id))


# Inline callback – Smena yangilash
@dp.callback_query(F.data.startswith("edit_smena"))
async def process_edit_smena(call: types.CallbackQuery):
    _, worker_id, smena = call.data.split(":")
    await db_conn.execute("UPDATE workers SET smena=$1 WHERE id=$2", int(smena), int(worker_id))
    await call.answer("✅ Smena yangilandi")
    await ask_edit_more(call.from_user.id, call, int(worker_id))


# Inline callback – Bekat yangilash
@dp.callback_query(F.data.startswith("changestation"))
async def process_change_station(call: types.CallbackQuery):
    _, worker_id, station_id = call.data.split(":")
    await db_conn.execute("UPDATE workers SET station_id=$1 WHERE id=$2", int(station_id), int(worker_id))
    await call.answer("✅ Bekat yangilandi")
    await ask_edit_more(call.from_user.id, call, int(worker_id))


# ================================
# FIO yangilash
@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "edit_fullname")
async def process_edit_fullname(message: types.Message):
    state = user_states[message.from_user.id]
    worker_id = state["worker_id"]

    await db_conn.execute("UPDATE workers SET full_name=$1 WHERE id=$2", message.text, worker_id)
    await message.answer("✅ F.I.O yangilandi")
    await ask_edit_more(message.from_user.id, message, worker_id)


# ================================
# Tabel yangilash
@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "edit_tabel")
async def process_edit_tabel(message: types.Message):
    state = user_states[message.from_user.id]
    worker_id = state["worker_id"]

    if not message.text.isdigit() or len(message.text) != 5:
        return await message.answer("❌ Tabel raqam 5 xonali son bo‘lishi kerak. Qayta kiriting:")

    await db_conn.execute("UPDATE workers SET tabel=$1 WHERE id=$2", message.text, worker_id)
    await message.answer("✅ Tabel yangilandi")
    await ask_edit_more(message.from_user.id, message, worker_id)


# ================================
# Rasmni yangilash
@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "edit_photo", F.photo)
async def process_edit_photo(message: types.Message):
    state = user_states[message.from_user.id]
    worker_id = state["worker_id"]

    # Eng sifatli variantni olish
    file_id = message.photo[-1].file_id

    await db_conn.execute("UPDATE workers SET photo=$1 WHERE id=$2", file_id, worker_id)
    await message.answer("✅ Rasm yangilandi")

    await ask_edit_more(message.from_user.id, message, worker_id)


# ================================
# O‘zgartirishdan keyin "Ha / Yo‘q" tugmasi
async def ask_edit_more(user_id, message_or_callback, worker_id):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Ha"), KeyboardButton(text="Yo‘q")]],
        resize_keyboard=True
    )
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer("🔄 Yana boshqa maydonni o‘zgartirasizmi?", reply_markup=kb)
    else:
        await message_or_callback.message.answer("🔄 Yana boshqa maydonni o‘zgartirasizmi?", reply_markup=kb)

    user_states[user_id] = {"state": "edit_more", "worker_id": worker_id}


# ================================
# ================================
# Ha / Yo‘q tugmalarini qayta ishlash
@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("state") == "edit_more")
async def edit_more_choice(message: types.Message):
    state = user_states[message.from_user.id]
    worker_id = state["worker_id"]

    if message.text == "Ha":
        await show_worker_fields(message.from_user.id, message, worker_id)

    elif message.text == "Yo‘q":
        # ✅ Saqlashdan oldin xodimning yangilangan ma’lumotlarini olib kelamiz
        worker = await db_conn.fetchrow("SELECT * FROM workers WHERE id=$1", worker_id)
        station_name = await db_conn.fetchval("SELECT name FROM stations WHERE id=$1", worker["station_id"])

        # Guruhga xabar yuborish
        await send_to_group(
            f"✏️ Xodim ma’lumotlari yangilandi!📌\n\n"
            f"👤 F.I.O: {worker['full_name']}\n"
            f"🔢 Tabel: {worker['tabel']}\n"
            f"💼 Lavozim: {worker['position']}\n"
            f"🕒 Smena: {worker['smena']}\n"
            f"🏢 Bekat: {station_name}"
        )

        # State tozalash
        user_states.pop(message.from_user.id, None)

        # ✅ Saqlangandan keyin bosh menyu qaytariladi
        await message.answer("✅ O‘zgarishlar saqlandi.", reply_markup=main_kb)

    else:
        await message.answer("❌ Faqat 'Ha' yoki 'Yo‘q' tugmasidan foydalaning.")



async def main(): 
    await setup_db() 
    await dp.start_polling(bot)
    
if __name__ == "__main__": 
    asyncio.run(main())
