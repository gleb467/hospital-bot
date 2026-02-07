import asyncio
import logging
import os
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

BOT_TOKEN = "8392067965:AAHt6PD2-gPXXFOGzf5CjS1bSMH8lE6HHyU"

logging.basicConfig(level=logging.INFO)
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Railway - из переменной окружения
google_creds_str = os.environ.get('GOOGLE_CREDENTIALS')
if not google_creds_str:
    raise ValueError("GOOGLE_CREDENTIALS переменная не найдена!")

google_creds = json.loads(google_creds_str)
creds = Credentials.from_service_account_info(google_creds, scopes=SCOPES)
client = gspread.authorize(creds)

sheet = client.open_by_key("13dKqRWCfg9CMcSYwCTXFPaN0b4uwdd4DY7frJnq2Qcg").get_worksheet(0)

class Form(StatesGroup):
    choosing_palata = State()
    entering_surname = State()
    choosing_patient_to_delete = State()

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Свободные койки")],
        [KeyboardButton(text="🏥 Палата 11"), KeyboardButton(text="🏥 Палата 12")],
        [KeyboardButton(text="➕ Поступление"), KeyboardButton(text="🗑 Выписать")]
    ],
    resize_keyboard=True
)

palata_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="11"), KeyboardButton(text="12")],
        [KeyboardButton(text="❌ Отмена")]
    ],
    resize_keyboard=True
)

def find_free_bed(palata: str) -> str:
    """Находит первую свободную койку в палате"""
    all_rows = sheet.get_all_values()
    data = all_rows[1:]
    
    occupied_beds = set()
    for row in data:
        if len(row) > 6 and row[1] == palata and row[6].strip() == "Лежит":
            occupied_beds.add(row[2])
    
    # Палата 11 имеет 7 коек, палата 12 имеет 10 коек
    max_beds = 7 if palata == "11" else 10
    
    for bed in range(1, max_beds + 1):
        if str(bed) not in occupied_beds:
            return str(bed)
    
    return "1"

def get_patient_display(surname: str, discharge: str, metka: str = "", sostoyanie: str = "") -> str:
    """Формирует строку отображения пациента с метками"""
    marks = ""
    
    if metka and metka.strip() and metka.strip() != "Нет":
        marks += metka.strip() + " "
    
    if sostoyanie and sostoyanie.strip():
        marks += sostoyanie.strip() + " "
    
    if marks:
        return f"{marks}{surname} — выписка {discharge}"
    else:
        return f"{surname} — выписка {discharge}"

def get_all_patients():
    """Получает всех лежачих пациентов"""
    all_rows = sheet.get_all_values()
    data = all_rows[1:] if len(all_rows) > 1 else []
    
    patients = []
    for idx, row in enumerate(data, start=2):
        if len(row) > 6 and row[6].strip() == "Лежит":
            patient_id = row[0] if len(row) > 0 else str(idx)
            palata = row[1] if len(row) > 1 else "?"
            koyka = row[2] if len(row) > 2 else "?"
            surname = row[3] if len(row) > 3 else "???"
            discharge = row[5] if len(row) > 5 else "не указана"
            metka = row[7] if len(row) > 7 else ""
            sostoyanie = row[8] if len(row) > 8 else ""
            
            patients.append({
                'row_num': idx,
                'id': patient_id,
                'palata': palata,
                'koyka': koyka,
                'surname': surname,
                'discharge': discharge,
                'metka': metka,
                'sostoyanie': sostoyanie
            })
    
    return patients

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Виктория Анатольевна, выберите действие:", reply_markup=keyboard)

@dp.message(lambda message: message.text == "➕ Поступление")
async def start_admission(message: types.Message, state: FSMContext):
    await state.set_state(Form.choosing_palata)
    await message.answer("Выберите палату:", reply_markup=palata_keyboard)

@dp.message(Form.choosing_palata, lambda message: message.text in ["11", "12"])
async def palata_chosen(message: types.Message, state: FSMContext):
    await state.update_data(palata=message.text)
    await state.set_state(Form.entering_surname)
    await message.answer(
        f"Палата {message.text} выбрана.\nТеперь напишите фамилию пациента:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True
        )
    )

@dp.message(Form.choosing_palata, lambda message: message.text == "❌ Отмена")
async def cancel_from_palata(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено", reply_markup=keyboard)

@dp.message(Form.entering_surname, lambda message: message.text == "❌ Отмена")
async def cancel_from_surname(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено", reply_markup=keyboard)

@dp.message(Form.entering_surname)
async def surname_entered(message: types.Message, state: FSMContext):
    data = await state.get_data()
    palata = data.get('palata')
    surname = message.text.strip()
    
    if not surname or len(surname) < 2:
        await message.answer("Введите корректную фамилию:")
        return
    
    koyka = find_free_bed(palata)
    today = datetime.now().strftime("%d.%m.%Y")
    discharge_date = (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y")
    
    all_rows = sheet.get_all_values()
    new_id = len(all_rows)
    
    try:
        sheet.append_row([
            str(new_id),
            palata,
            koyka,
            surname,
            today,
            discharge_date,
            "Лежит",
            "",
            ""
        ])
        
        await message.answer(
            f"✅ Пациент добавлен!\n\n"
            f"Фамилия: {surname}\n"
            f"Палата: {palata}, койка: {koyka}\n"
            f"Поступил: {today}\n"
            f"Выписка: {discharge_date} (через 7 дней)\n\n"
            f"💡 Метки и состояние можно установить в таблице",
            reply_markup=keyboard
        )
        await state.clear()
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=keyboard)
        await state.clear()

@dp.message(lambda message: message.text == "🗑 Выписать")
async def start_discharge(message: types.Message, state: FSMContext):
    patients = get_all_patients()
    
    if not patients:
        await message.answer("Нет пациентов для выписки", reply_markup=keyboard)
        return
    
    buttons = []
    for p in patients:
        display_text = f"{p['surname']} (П{p['palata']}, К{p['koyka']})"
        if len(display_text) > 30:
            display_text = display_text[:27] + "..."
        
        buttons.append([InlineKeyboardButton(
            text=display_text,
            callback_data=f"delete_{p['row_num']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")])
    
    keyboard_inline = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        "Выберите пациента для выписки:",
        reply_markup=keyboard_inline
    )

@dp.callback_query(lambda c: c.data.startswith("delete_"))
async def process_delete(callback: types.CallbackQuery):
    row_num = int(callback.data.split("_")[1])
    
    try:
        all_rows = sheet.get_all_values()
        if row_num <= len(all_rows):
            patient_data = all_rows[row_num - 1]
            surname = patient_data[3] if len(patient_data) > 3 else "???"
            palata = patient_data[1] if len(patient_data) > 1 else "?"
            koyka = patient_data[2] if len(patient_data) > 2 else "?"
            
            sheet.update_cell(row_num, 7, "Выписан")
            
            await callback.message.edit_text(
                f"✅ Пациент выписан!\n\n"
                f"Фамилия: {surname}\n"
                f"Палата: {palata}, койка: {koyka}\n"
                f"Койка теперь свободна."
            )
            
            await callback.message.answer(
                "Выберите действие:",
                reply_markup=keyboard
            )
        else:
            await callback.message.edit_text("❌ Ошибка: пациент не найден")
            
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при выписке: {e}")
    
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cancel_delete")
async def cancel_delete(callback: types.CallbackQuery):
    await callback.message.edit_text("Отменено")
    await callback.message.answer("Выберите действие:", reply_markup=keyboard)
    await callback.answer()

@dp.message(lambda message: message.text in ["📊 Свободные койки", "🏥 Палата 11", "🏥 Палата 12"])
async def handle_view_buttons(message: types.Message, state: FSMContext):
    await state.clear()
    
    all_rows = sheet.get_all_values()
    data = all_rows[1:] if len(all_rows) > 1 else []

    if message.text == "📊 Свободные койки":
        lying = sum(1 for row in data if len(row) > 6 and row[6].strip() == "Лежит")
        total = 17
        free = total - lying
        await message.answer(
            f"📊 Статистика коек:\n\n"
            f"Занято: {lying}\n"
            f"Свободно: {free}\n"
            f"Всего: {total}"
        )

    elif message.text == "🏥 Палата 11":
        patients = []
        for row in data:
            if len(row) > 6 and row[1] == "11" and row[6].strip() == "Лежит":
                surname = row[3] if len(row) > 3 else "???"
                koyka = row[2] if len(row) > 2 else "?"
                discharge = row[5] if len(row) > 5 else "не указана"
                metka = row[7] if len(row) > 7 else ""
                sostoyanie = row[8] if len(row) > 8 else ""
                
                patient_info = get_patient_display(surname, discharge, metka, sostoyanie)
                patients.append(f"К{koyka}: {patient_info}")
        
        if patients:
            response = "🏥 Палата 11:\n\n" + "\n".join(patients)
        else:
            response = "В палате 11 нет пациентов."
        await message.answer(response)

    elif message.text == "🏥 Палата 12":
        patients = []
        for row in data:
            if len(row) > 6 and row[1] == "12" and row[6].strip() == "Лежит":
                surname = row[3] if len(row) > 3 else "???"
                koyka = row[2] if len(row) > 2 else "?"
                discharge = row[5] if len(row) > 5 else "не указана"
                metka = row[7] if len(row) > 7 else ""
                sostoyanie = row[8] if len(row) > 8 else ""
                
                patient_info = get_patient_display(surname, discharge, metka, sostoyanie)
                patients.append(f"К{koyka}: {patient_info}")
        
        if patients:
            response = "🏥 Палата 12:\n\n" + "\n".join(patients)
        else:
            response = "В палате 12 нет пациентов."
        await message.answer(response)

@dp.message()
async def handle_other(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Используйте кнопки ниже", reply_markup=keyboard)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
