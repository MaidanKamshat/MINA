# MINA v2.10 — Multi-store Voice Shopping Fix

## Что было найдено

Пример пользовательской команды от 21 ноября 2026 года:

> Mina, add strawberries and yogurt to my Target shopping list, and rice and olive oil to my Trader Joe's shopping list.

В предыдущей версии все четыре позиции отобразились в Trader Joe's, включая ошибочно распознанную позицию `yogurt to my Target shopping list`. Сценарий **multi-store** считается **FAILED** в предыдущей версии. Со скриншота нельзя определить, нажималась ли кнопка подтверждения: утверждать, что запись прошла без подтверждения, было бы некорректно.

## Что исправлено

1. Новая строгая маршрутизация записи по нескольким магазинам; имена магазинов и позиции связываются по каждому фрагменту команды, а не по первому/последнему упомянутому магазину.
2. Если запрос на добавление затрагивает два или три магазина, но его нельзя однозначно разделить, MINA **не сохраняет ничего** и просит уточнить.
3. Перед записью показывается один preview с отдельными блоками Target / Trader Joe's / Costco. Запись возможна **только после отдельного подтверждения** кнопкой или явной подтверждающей голосовой командой. Отмена ничего не сохраняет.
4. При подтверждении все изменения готовятся на копии локальных данных и сохраняются за одну операцию после успешной обработки всех позиций; сбой одной позиции не приводит к частичной записи.
5. В Settings → Family Hub → Shopping lists появилась секция `Remove one shopping item` для точечного удаления ошибочно добавленной позиции с явной галочкой подтверждения.
6. После подтверждённого изменения локального списка больше не показывается ошибочная подпись `Read-only response`: вместо неё `Confirmed local update · not an external write`.

## Установка

Это **patch**, а не самостоятельный проект. Нужна уже работающая папка MINA v2.9.1. Патч меняет **только** `streamlit_app.py` и добавляет `mina_multi_store_v210.py` и тест, **не содержит** `local_data/`, OAuth, ключи или персональные данные. Предыдущий `mina_calendar_v27.py` hotfix v2.9.1 остаётся на месте.

1. Останови Streamlit через `Control + C`.
2. Сделай резервную копию работающего `streamlit_app.py`.
3. Распакуй патч в существующую папку проекта:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_backup_v291.py
unzip -o ~/Downloads/MINA_v2_10_Multi_Store_Shopping_Fix.zip -d .
python -m unittest -v test_mina_multi_store_v210.py
python -m streamlit run streamlit_app.py
```

Ожидаемый локальный тест: `Ran 26 tests`, `OK`. При ошибке тестов не продолжай тестирование записи: пришли последние строки Terminal.

## Восстановить списки после предыдущего теста

По скриншоту в Trader Joe's есть уже существовавшие `spinach pasta`, `lavender soap`, корректно назначенные Trader Joe's `rice`, `olive oil` и две ошибочные записи:

- `strawberries` — должны быть в Target;
- `yogurt to my Target shopping list` — ошибочное название позиции, в Target нужен просто `yogurt`.

В Settings → Family Hub → Shopping lists выбери Trader Joe's, открой **Remove one shopping item**. Выбери и удали **только** `strawberries`; затем таким же образом **только** `yogurt to my Target shopping list`. Не удаляй `spinach pasta`, `lavender soap`, `rice` и `olive oil`. Ничего автоматически не очищается установкой патча.

После этого можно протестировать новое разбиение с **другими** товарами, чтобы не дублировать уже существующие:

> Mina, add dish soap and toothpaste to my Target shopping list, and frozen mango and pita bread to my Trader Joe's shopping list.

Ожидаемый **preview до подтверждения**:
- Target: `dish soap`, `toothpaste`;
- Trader Joe's: `frozen mango`, `pita bread`.

**Сначала прислать preview; пока не нажимать Confirm.**

## Проверки и границы

- Локально `26/26` тестов парсинга, атомарного применения с тестовым `add_item`, безопасного удаления и статической проверки интерфейсных веток — успешно.
- `python -m py_compile` пройден для `streamlit_app.py`, `mina_multi_store_v210.py` и теста.
- **Не проверено на данном компьютере:** полный запуск Streamlit с твоей исходной папкой (модули MINA из первоначального baseline не вложены в архив), реальная транскрипция микрофона, сохранение локального `local_data` на твоём Mac.
- Поддерживаемый шаблон команд: `add ITEM and ITEM to my STORE shopping list, and ITEM and ITEM to my OTHER STORE shopping list` (до трёх магазинов). Намеренно не угадываем сложные или неоднозначные фразы; безопасно просим переформулировать.
