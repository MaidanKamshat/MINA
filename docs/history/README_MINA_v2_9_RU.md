# MINA v2.9 — Voice → Calendar routing fix

Это небольшой **патч существующего проекта MINA v2.8**, не самостоятельное приложение. Нужна папка на Mac со всеми установленными модулями MINA, которая уже успешно запускала v2.8 и Google Calendar.

## Что изменилось

- Голосовая транскрипция `10 a.m.`, `10 A.M.`, `10 AM`, `10am`, `10:00 a.m.`, а также `ten in the morning` приводится к единому формату для календарного парсера. Транскрипт в чате сохраняется без подмены.
- `for 15 minutes` / `for fifteen minutes` / `for half an hour` формируют **окончание события**, а не неявные 60 минут.
- Явные даты вида `Monday, November 30th` обрабатываются даже при пунктуации и суффиксе `th`; противоречащие день недели и дата не угадываются.
- Если календарный запрос распознан как намерение, но безопасно извлечь время/дату не удалось, MINA просит уточнить данные, а не сообщает неверно, что инструмент Google Calendar не подключён.
- Существующий механизм `Preview → Explicit approval → Local save → optional Google write` сохранён. Напоминания Google **24 часа и 2 часа** сохранены. Отправка писем и прочие составные запросы не проходят через календарный парсер.
- Welcome Page, меню Settings, текущие Google OAuth файлы, локальные сохранённые события и Family Hub не меняются.

## Установка

1. Останови Streamlit в Terminal сочетанием `Control+C`.
2. В той же существующей папке проекта (не в новой пустой) выполни:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_backup_v28.py
cp mina_calendar_v27.py mina_calendar_v27_backup_v28.py
unzip -o ~/Downloads/MINA_v2_9_Voice_Calendar_Fix_patch.zip -d .
python -m unittest -v test_mina_voice_calendar_v29.py
python -m streamlit run streamlit_app.py
```

Если текущая папка MINA у тебя другая, замени только путь в команде `cd`.

В ZIP всего **4 файла**: два исправленных Python-файла, офлайн-тест и этот README. Он не содержит `local_data/`, OAuth-токены, секреты, ключи или личные данные. **Не удаляй и не переноси** свою папку `local_data/`.

## Проверка в MINA

После запуска произнеси через микрофон:

> Mina, schedule a test appointment on Monday, November 30th at 10 a.m. for 15 minutes. Remind me one day and two hours before.

**Ожидаемый Preview:** `Test appointment` • `2026-11-30` • `10:00 AM`–`10:15 AM`; напоминания November 29 at 10:00 AM и November 30 at 8:00 AM.

Не нажимай `Confirm & save` до проверки. Появление Preview ещё не означает, что событие записано в Google.

## Проверки и ограничения

Локально проверены синтаксис обоих обновлённых модулей и набор регрессионных сценариев с тестовыми заглушками отсутствующих модулей прежней версии. Не проверялись фактическая голосовая транскрипция на пользовательском Mac или live-взаимодействие с OAuth/Google Calendar — их нужно проверить вручную после установки. В текущей модели событие, которое пересекает полночь, не создаётся без уточнения.
