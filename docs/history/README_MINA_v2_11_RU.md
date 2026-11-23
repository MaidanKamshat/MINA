# MINA v2.11 — Voice Shopping List Removal (safe hotfix)

## Почему нужна новая версия

21 ноября 2026 пользователь проверил голосовую команду:

> Mina, remove toothpaste from my Target shopping list.

Версия v2.10 ответила: `I can prepare that change, but no list/calendar/email write tool is connected.` Это **FAILED** для голосового удаления (сообщение общего блокировщика), а не свидетельство отсутствия локальных списков. Существующее добавление товаров и Google Calendar ранее проверены отдельно.

## Что исправлено

- Добавлен специальный маршрутизатор **одного локального удаления**: `remove toothpaste from my Target shopping list`, `delete ... from ...`, `take ... off ...`.
- Определяются ровно **один магазин** (Costco, Target, Trader Joe's) и **одна существующая позиция** по имени без неявных догадок. Если совпадений нет или их несколько, MINA объясняет проблему и **ничего не изменяет**.
- До записи показывается Preview: **Store**, **Remove exactly one item**, **Nothing has been removed**.
- Удаление требует отдельного `Confirm item removal` или явного голосового/текстового подтверждения по существующему механизму `Confirm my local update`. `Cancel change` сохраняет исходный список.
- При подтверждении повторно проверяются ID и исходное название позиции; если список изменился после preview, операция безопасно отклоняется.
- Другие магазины, товары, календарь, OAuth, дизайн и существующие данные остаются без изменений. Новых внешних разрешений не нужно.

## Установка (поверх работающей MINA v2.10)

1. Остановить Streamlit в терминале клавишами `Control + C`.
2. Сделать резервную копию текущего `streamlit_app.py` и распаковать архив в существующую папку проекта:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_backup_v210.py
unzip -o ~/Downloads/MINA_v2_11_Voice_Shopping_Removal_Fix.zip -d .
python -m unittest -v test_mina_list_removal_v211.py test_mina_multi_store_v210.py
python -m streamlit run streamlit_app.py
```

Ожидаемый тест: `Ran 57 tests ... OK` (на проверочной копии в среде разработчика). Если тесты на Mac падают, **не продолжать удаление**, показать Traceback и результаты теста.

## Ручной E2E-тест

Повторить **голосом**:

> Mina, remove toothpaste from my Target shopping list.

Ожидаемый Preview:

```
Proposed local shopping-list removal (not saved yet)
Store: Target
Remove exactly one item: toothpaste
Nothing has been removed.
[Confirm item removal]  [Cancel change]
```

Перед подтверждением проверить, что Target → toothpaste по-прежнему присутствует. Сначала прислать screenshot Preview, **не подтверждать**. После проверки подтвердить и убедиться в Settings, что **toothpaste удалён из Target**, **dish soap остался**, и списки Costco и Trader Joe's не изменились.

## Что протестировано / границы

- `57/57` локальных тестов Python после добавления v2.11 к v2.10 — PASS; включая 31 новый тест v2.11, 26 регрессионных тестов v2.10.
- Синтаксис `streamlit_app.py` и нового парсера скомпилирован.
- Проверка не включает реальную транскрипцию с микрофона или полную установку на Mac: базовые модули MINA из папки пользователя не вложены в архив.
- Патч содержит **только** код и тесты, без OAuth-токенов, ключей или `local_data/`.
- Сложные команды на несколько удалений и удаление несуществующих позиций намеренно не выполняются автоматически.
