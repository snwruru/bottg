import os
import asyncio
from math import ceil
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

BOT_TOKEN = "8636727855:AAEIRF7icpCJfQLEllugM9tgnbEaOAPEXp0"



class Form(StatesGroup):
    choosing_object = State()
    waiting_area = State()
    waiting_thickness = State()
    waiting_distance = State()


def start_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Квартира"), KeyboardButton(text="Частный дом")],
            [KeyboardButton(text="Начать заново")],
        ],
        resize_keyboard=True
    )


def restart_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Начать заново")]
        ],
        resize_keyboard=True
    )


def distance_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Без учета расстояния")],
            [KeyboardButton(text="Начать заново")],
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


def build_pump_kp(area: float, thickness_mm: float, distance_km: Optional[float]) -> str:
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

    return f"""Коммерческое предложение

Стоимость устройства полусухой стяжки составляет:
{total:.0f} ₽
({price_per_m2:.0f} ₽/м²)

В стоимость работ включено:
- Доставка материала
- нарезка деформационных швов
- затирка поверхности
- монтаж демпферной ленты
- добавление фиброволокна
- укладка плёнки под стяжку
- укрывочная плёнка

В работе используются:
- мытый Багаевский песок
- цемент марки М500

Гарантия на выполненные работы — 5 лет.
Связаться с нами можно по номеру +7(903)244-16-66 Дмитрий"""


def build_semi_manual_kp(area: float, thickness_mm: float) -> str:
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

    return f"""Коммерческое предложение

Стоимость устройства полусухой стяжки составляет:
{total:.0f} ₽
({price_per_m2:.0f} ₽/м²)

В стоимость работ включено:
- нарезка деформационных швов
- затирка поверхности
- монтаж демпферной ленты
- добавление фиброволокна
- укладка плёнки под стяжку
- укрывочная плёнка

В работе используются:
- мытый Багаевский песок
- цемент марки М500

Гарантия на выполненные работы — 5 лет.
Связаться с нами можно по номеру +7(903)244-16-66 Дмитрий """


dp = Dispatcher(storage=MemoryStorage())


async def reset_dialog(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Form.choosing_object)
    await message.answer(
        "Здравствуйте. Какой у вас объект?",
        reply_markup=start_keyboard()
    )


@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await reset_dialog(message, state)


@dp.message()
async def global_buttons_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text in ["Начать заново"]:
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


async def object_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text not in ["Квартира", "Частный дом"]:
        await message.answer(
            "Пожалуйста, выберите объект кнопкой ниже.",
            reply_markup=start_keyboard()
        )
        return

    await state.update_data(object_type=text)
    await state.set_state(Form.waiting_area)
    await message.answer(
        "Введите площадь в м²:",
        reply_markup=restart_keyboard()
    )


async def area_handler(message: Message, state: FSMContext):
    area = parse_number(message.text or "")
    if area is None or area <= 0:
        await message.answer("Введите корректную площадь, например: 85")
        return

    await state.update_data(area=area)
    await state.set_state(Form.waiting_thickness)
    await message.answer("Введите толщину стяжки в мм, например: 70")


async def thickness_handler(message: Message, state: FSMContext):
    thickness = parse_number(message.text or "")
    if thickness is None or thickness <= 0:
        await message.answer("Введите корректную толщину, например: 70")
        return

    data = await state.get_data()
    object_type = data["object_type"]
    area = data["area"]

    if object_type == "Частный дом":
        await state.update_data(thickness=thickness)
        await state.set_state(Form.waiting_distance)
        await message.answer(
            "Введите расстояние от МКАД в км или нажмите «Без учета расстояния».",
            reply_markup=distance_keyboard()
        )
        return

    kp_text = build_semi_manual_kp(area=area, thickness_mm=thickness)
    await message.answer(kp_text, reply_markup=restart_keyboard())
    await state.clear()


async def distance_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "Без учета расстояния":
        distance = None
    else:
        parsed = parse_number(text)
        if parsed is None or parsed < 0:
            await message.answer("Введите корректное расстояние, например: 25")
            return
        distance = parsed

    data = await state.get_data()
    area = data["area"]
    thickness = data["thickness"]

    kp_text = build_pump_kp(area=area, thickness_mm=thickness, distance_km=distance)
    await message.answer(kp_text, reply_markup=restart_keyboard())
    await state.clear()


async def main():
    print("Бот запускается...")
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())