# MINA v2.15.1 — Final Welcome Page Polish

**Дата:** November 22, 2026. **База:** рабочая MINA v2.15 Lite.

## Что изменилось

- Буквы **M / I / N / A** в `My Intelligent Navigation Assistant` и слово **MINA** в заголовке используют единый editorial navy `#0D1B2A`.
- Оставшиеся буквы подписи окрашены в светлый, приглушённый blue-gray `#8A9AA9`.
- `How it works ▾` и `Features ▾` открывают **небольшие всплывающие карточки (Streamlit popovers)** прямо у кнопки. Вместо неочевидного перехода к секции ниже — мгновенная реакция на клик. Hover/focus сделаны аккуратными, с учётом reduced motion.
- `Explore MINA`, `Get started`, `Settings`, логика чата, голос, Reminders, Memory, Calendar, Planner и все данные пользователя не менялись.

## Установка поверх текущей v2.15

Закрой Streamlit в Terminal через **Control + C**. Скачай ZIP в **~/Downloads**, затем выполни:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
mkdir -p .mina_backup_before_v2151
cp -p streamlit_app.py .mina_backup_before_v2151/
unzip -o ~/Downloads/MINA_v2_15_1_Final_Welcome_UI_Polish.zip -d .
python -m unittest -q test_mina_welcome_polish_v2151.py test_mina_v215.py
python -m streamlit run streamlit_app.py
```

Важно: ZIP меняет `streamlit_app.py` и добавляет CSS/тест; **не удаляй** существующие модули и `.env`. Нужны прежние `mina_theme_v2_1.css`, `mina_theme_v2_2.css`, `mina_theme_v2_8.css` на твоём Mac. Они уже есть в рабочем проекте.

## Quick acceptance test (1–2 минуты)

1. Открой welcome page, убедись, что **M/I/N/A** выделены тем же тёмно-синим цветом, что и **MINA**, остальные буквы подписи приглушены.
2. Нажми **How it works ▾**: небольшая карточка появляется **рядом с кнопкой**, а не внизу страницы; закрой её нажатием за пределами.
3. Нажми **Features ▾**: видны функции, включая Reminders и local history. Карточка закрывается обычным образом.
4. Нажми **Get started** и убедись, что чат открывается; затем **Settings** — проверить, что настройки не нарушены.

## Если нужен быстрый откат

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
cp -p .mina_backup_before_v2151/streamlit_app.py ./streamlit_app.py
python -m streamlit run streamlit_app.py
```

Дополнительный CSS-файл можно оставить: старая версия его не загружает.

## Validation / caveats

- **29/29** локальных unit/static тестов прошли (включая v2.15). `py_compile` для основного файла и новых модулей — PASS.
- Полная визуальная проверка Streamlit на Mac не проводилась здесь; нужна короткая проверка после установки.
- Для максимальной надёжности использован **native Streamlit popover**, а не JavaScript scroll-animation. Это отличается от ранее обсуждавшегося варианта smooth scroll, но решает ту же UX-проблему — кнопка сразу даёт видимый результат.
- Не добавлялись новые возможности и не изменялась модель LLM. Это исключительно финальный дизайн-патч перед сдачей.
