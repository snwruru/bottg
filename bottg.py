import asyncio
from math import ceil
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = "8636727855:AAEIRF7icpCJfQLEllugM9tgnbEaOAPEXp0"
ADMIN_ID = 127016693


class Form(StatesGroup):
    choosing_object = State()
    waiting_area = State()
    waiting_thickness = State()
    waiting_distance = State()
    waiting_phone = State()


def start_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Квартира"), KeyboardButton(text="🏡 Частный дом")],
            [KeyboardButton(text="🔄 Начать заново")],
        ],
        resize_keyboard=True
    )


def restart_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Начать заново")]
        ],
        resize_keyboard=True
    )


def distance_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Без учета расстояния")],
            [KeyboardButton(text="🔄 Начать заново")],
        ],
        resize_keyboard=True
    )


def result_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Оставить заявку")],
            [KeyboardButton(text="🔄 Начать заново")],
        ],
        resize_keyboard=True
    )


def parse_number(text: str) -> Optional[float]:
    text = text.strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def is_valid_phone(text: str) -> bool:
    digits = "".join(ch for ch in text if ch.isdigit())
    return len(digits) >= 10


def build_pump_kp(area: float, thickness_mm: float, distance_km: Optional[float]) -> tuple[str, float]:
    volume = area * thickness_mm / 1000.0

    cement_bags = volume * 5
    cement_cost = cement_bags * 460

    cement_weight_kg = cement_bags * 50
    if cement_weight_kg <= 3000:
        cement_delivery = 5000.0
    elif cement_weight_kg <= 5000:
        cement_delivery = 10000.0
    else:
        cement_delivery = 15000.0

    if volume <= 11:
        sand_cost = 1600 * volume + 6500
    else:
        sand_cost = 1700 * volume + 8500

    workers = max(area * 350, 35000.0)

    if area <= 150.0:
        profit = 25000.0
    elif area <= 200.0:
        profit = 35000.0
    elif area <= 300.0:
        profit = 40000.0
    else:
        profit = 45000.0

    fuel = 5000.0
    distance_cost = 0.0 if distance_km is None else 10000.0 + distance_km * 200.0

    total = cement_cost + cement_delivery + sand_cost + fuel + workers + profit + distance_cost
    price_per_m2 = total / area

    kp = f"""🏗 Коммерческое предложение
━━━━━━━━━━━━━━━━━━━━

💰 Общая стоимость: {total:.0f} ₽
📊 Цена за 1м²: {price_per_m2:.0f} ₽/м²
📐 Площадь: {area} м²
📏 Толщина: {thickness_mm} мм

━━━━━━━━━━━━━━━━━━━━
✅ В стоимость включено:

• Доставка материала
• Нарезка деформационных швов
• Затирка поверхности
• Монтаж демпферной ленты
• Добавление фиброволокна
• Укладка плёнки под стяжку
• Укрывочная плёнка

━━━━━━━━━━━━━━━━━━━━
🔧 Материалы:

• Мытый Багаевский песок
• Цемент марки М500

🛡 Гарантия на выполненные работы — 5 лет"""

    return kp, total


def build_semi_manual_kp(area: float, thickness_mm: float) -> tuple[str, float]:
    volume = area * thickness_mm / 1000.0

    sand_bags = volume * 50
    sand_cost = sand_bags * 60

    cement_bags = volume * 5
    cement_cost = cement_bags * 460

    delivery_trips = ceil(max(sand_bags / 100.0, cement_bags / 10.0))
    delivery_cost = delivery_trips * 5000

    loaders_cost = volume * 1.6 * 1500
    fuel = 2000.0
    workers = 30000.0
    profit = 15000.0

    total = sand_cost + cement_cost + delivery_cost + loaders_cost + fuel + workers + profit
    price_per_m2 = total / area

    kp = f"""🏗 Коммерческое предложение
━━━━━━━━━━━━━━━━━━━━

💰 Общая стоимость: {total:.0f} ₽
📊 Цена за 1м²: {price_per_m2:.0f} ₽/м²
📐 Площадь: {area} м²
📏 Толщина: {thickness_mm} мм

━━━━━━━━━━━━━━━━━━━━
✅ В стоимость включено:

• Нарезка деформационных швов
• Затирка поверхности
• Монтаж демпферной ленты
• Добавление фиброволокна
• Укладка плёнки под стяжку
• Укрывочная плёнка

━━━━━━━━━━━━━━━━━━━━
🔧 Материалы:

• Мытый Багаевский песок
• Цемент марки М500

🛡 Гарантия на выполненные работы — 5 лет"""

    return kp, total


dp = Dispatcher(storage=MemoryStorage())

# Хранилище активных задач: user_id -> asyncio.Task
# Нужно чтобы отменять задачи если клиент оставил заявку раньше
pending_tasks: dict[int, list[asyncio.Task]] = {}


async def schedule_followup(bot: Bot, user_id: int, state: FSMContext, kp_text: str,
                             area: float, thickness: float, total: float,
                             object_type: str, username: str):
    """
    Через 30 сек — уведомление администратору с расчётом.
    Через 60 сек — сообщение клиенту с предложением связаться.
    Задачи отменяются если клиент оставит заявку раньше.
    """
    try:
        # --- 30 секунд: уведомление администратору ---
        await asyncio.sleep(30)

        # Проверяем, не оставил ли клиент заявку за это время
        current_state = await state.get_state()
        if current_state != Form.waiting_phone.state:
            return  # Клиент уже оставил заявку или сбросил диалог

        text_to_admin = (
            f"👀 Клиент получил расчёт, но заявку не оставил\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Пользователь: {user_id} ({username})\n"
            f"🏠 Объект: {object_type}\n"
            f"📐 Площадь: {area:.0f} м²\n"
            f"📏 Толщина: {thickness:.0f} мм\n"
            f"💰 Стоимость: {total:.0f} ₽\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{kp_text}"
        )
        await bot.send_message(chat_id=ADMIN_ID, text=text_to_admin)

        # --- ещё 150 секунд (итого 180 от расчёта): сообщение клиенту ---
        await asyncio.sleep(150)

        current_state = await state.get_state()
        if current_state != Form.waiting_phone.state:
            return  # Клиент успел оставить заявку

        followup_text = (
            "Мы не стараемся просто назвать минимальную цену \u00abдля заманухи\u00bb. "
            "Наша задача \u2014 сразу показать более реалистичный расчёт. "
            "Но по многим объектам можно подобрать более выгодное решение. "
            "Позвоните, и я предложу оптимальный вариант под ваш бюджет. "
            '<a href="tel:+79032441666">+7\u00a0903\u00a0244-16-66</a> Дмитрий'
        )
        await bot.send_message(
            chat_id=user_id,
            text=followup_text,
            parse_mode="HTML"
        )

    except asyncio.CancelledError:
        pass  # Задача отменена — всё нормально
    finally:
        # Чистим словарь задач
        pending_tasks.pop(user_id, None)


def cancel_pending_tasks(user_id: int):
    """Отменяет отложенные задачи для пользователя (если клиент оставил заявку)."""
    tasks = pending_tasks.pop(user_id, [])
    for task in tasks:
        task.cancel()


async def reset_dialog(message: Message, state: FSMContext) -> None:
    cancel_pending_tasks(message.from_user.id)
    await state.clear()
    await state.set_state(Form.choosing_object)
    await message.answer(
        "👋 Здравствуйте!\n\n"
        "Я помогу рассчитать стоимость полусухой стяжки пола.\n\n"
        "🏠 Какой у вас объект?",
        reply_markup=start_keyboard()
    )


async def send_kp_and_schedule(message: Message, state: FSMContext, kp: str, total: float):
    """Отправляет расчёт клиенту и запускает отложенные задачи."""
    await message.answer(kp, reply_markup=result_keyboard())

    data = await state.get_data()
    area = data.get("area", 0)
    thickness = data.get("thickness", 0)
    object_type = "Квартира" if data.get("object_type") == "flat" else "Частный дом"
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "нет username"

    bot: Bot = message.bot

    # Отменяем предыдущие задачи на случай повторного расчёта
    cancel_pending_tasks(user_id)

    task = asyncio.create_task(
        schedule_followup(
            bot=bot,
            user_id=user_id,
            state=state,
            kp_text=kp,
            area=area,
            thickness=thickness,
            total=total,
            object_type=object_type,
            username=username,
        )
    )
    pending_tasks[user_id] = [task]


@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await reset_dialog(message, state)


@dp.message()
async def global_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text in ["🔄 Начать заново", "Начать заново"]:
        await reset_dialog(message, state)
        return

    current_state = await state.get_state()

    if current_state is None:
        await reset_dialog(message, state)
        return

    if current_state == Form.choosing_object.state:
        await object_handler(message, state)
    elif current_state == Form.waiting_area.state:
        await area_handler(message, state)
    elif current_state == Form.waiting_thickness.state:
        await thickness_handler(message, state)
    elif current_state == Form.waiting_distance.state:
        await distance_handler(message, state)
    elif current_state == Form.waiting_phone.state:
        await phone_handler(message, state)


async def object_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text not in ["🏢 Квартира", "🏡 Частный дом", "Квартира", "Частный дом"]:
        await message.answer(
            "🏠 Пожалуйста, выберите тип объекта кнопкой ниже:",
            reply_markup=start_keyboard()
        )
        return

    object_type = "flat" if "Квартира" in text else "house"
    await state.update_data(object_type=object_type)
    await state.set_state(Form.waiting_area)
    await message.answer(
        "📐 Введите площадь помещения в м²:\n\nНапример: 85",
        reply_markup=restart_keyboard()
    )


async def area_handler(message: Message, state: FSMContext):
    area = parse_number(message.text or "")
    if area is None or area <= 0:
        await message.answer("⚠️ Введите корректную площадь, например: 85")
        return

    await state.update_data(area=area)
    await state.set_state(Form.waiting_thickness)
    await message.answer("📏 Введите толщину стяжки в мм:\n\nНапример: 70")


async def thickness_handler(message: Message, state: FSMContext):
    thickness = parse_number(message.text or "")
    if thickness is None or thickness <= 0:
        await message.answer("⚠️ Введите корректную толщину, например: 70")
        return

    data = await state.get_data()
    object_type = data["object_type"]
    area = data["area"]

    await state.update_data(thickness=thickness)

    if object_type == "house":
        await state.set_state(Form.waiting_distance)
        await message.answer(
            "🗺 Введите расстояние от МКАД в км или нажмите кнопку ниже:",
            reply_markup=distance_keyboard()
        )
        return

    kp, total = build_semi_manual_kp(area=area, thickness_mm=thickness)
    await state.update_data(last_kp=kp, last_total=total)
    await state.set_state(Form.waiting_phone)
    await send_kp_and_schedule(message, state, kp, total)


async def distance_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "Без учета расстояния":
        distance = None
    else:
        parsed = parse_number(text)
        if parsed is None or parsed < 0:
            await message.answer("⚠️ Введите корректное расстояние, например: 25")
            return
        distance = None if parsed == 0 else parsed

    data = await state.get_data()
    area = data["area"]
    thickness = data["thickness"]

    kp, total = build_pump_kp(area=area, thickness_mm=thickness, distance_km=distance)
    await state.update_data(last_kp=kp, last_total=total)
    await state.set_state(Form.waiting_phone)
    await send_kp_and_schedule(message, state, kp, total)


async def phone_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "📋 Оставить заявку":
        await message.answer(
            "Отлично 👍\n\n📞 Введите ваш номер телефона, чтобы мы могли с вами связаться:\n\nНапример: +7 999 123-45-67",
            reply_markup=restart_keyboard()
        )
        return

    if not is_valid_phone(text):
        await message.answer("⚠️ Введите корректный номер телефона, например: +7 999 123-45-67")
        return

    # Клиент оставил заявку — отменяем отложенные уведомления
    cancel_pending_tasks(message.from_user.id)

    data = await state.get_data()
    phone = text
    kp_text = data.get("last_kp", "")
    area = data.get("area", 0)
    thickness = data.get("thickness", 0)
    total = data.get("last_total", 0)
    object_type = "Квартира" if data.get("object_type") == "flat" else "Частный дом"
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "нет username"

    text_to_admin = f"""🔥 Новая заявка!
━━━━━━━━━━━━━━━━━━━━
👤 Пользователь: {user_id} ({username})
📞 Телефон: {phone}
🏠 Объект: {object_type}
📐 Площадь: {area:.0f} м²
📏 Толщина: {thickness:.0f} мм
💰 Стоимость: {total:.0f} ₽
━━━━━━━━━━━━━━━━━━━━

{kp_text}
"""

    bot: Bot = message.bot
    await bot.send_message(chat_id=ADMIN_ID, text=text_to_admin)

    await state.clear()
    await message.answer(
        "✅ Заявка отправлена! Мы скоро свяжемся с вами 🙌",
        reply_markup=restart_keyboard()
    )


async def main():
    print("Бот запускается...")
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
