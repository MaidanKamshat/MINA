# MINA v2.15.4 — Final Welcome Tagline Text

Установить поверх **v2.15.3**. В этом UI-only patch меняется исключительно одна фраза на Welcome Page. Не меняет CSS, цвета, popup-меню, backend, Memory, Reminders, маршруты и подтверждения.

**Было:** `Plan your day, capture tasks, and make room for what matters.`

**Стало:** `Plan your day, capture tasks, and make room for what truly matters.`

В исходнике сохранён визуальный перенос строки после `and` для оформления на экране, но текст предложения соответствует новой фразе.

## Установка на Mac

Остановите Streamlit (Control + C), скачайте ZIP в Downloads.

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
mkdir -p .mina_backup_before_v2154
cp -p streamlit_app.py .mina_backup_before_v2154/
unzip -o ~/Downloads/MINA_v2_15_4_Welcome_Tagline_Copy.zip -d .
python -m unittest -q test_mina_welcome_tagline_v2154.py
python -m streamlit run streamlit_app.py
```

Проверить текст Welcome Page, прежний насыщенный teal у MINA и M/I/N/A, popover Features/How it works, Get started.

## Откат

```bash
cp -p .mina_backup_before_v2154/streamlit_app.py .
```
