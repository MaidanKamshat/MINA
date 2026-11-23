# MINA v2.15.2 — Restore Original Brand Accent (Welcome Page)

**Основа:** рабочая v2.15.1 (поповеры `How it works` и `Features` оставлены без изменений).

## Исправлено

- Удалено ошибочное переопределение navy `#0D1B2A` для основного слова **MINA** в `Welcome, I’m MINA`. Исходный акцентный цвет теперь снова задают сохранённые на Mac файлы темы `mina_theme_v2_1.css`, `mina_theme_v2_2.css` и `mina_theme_v2_8.css`.
- Первые буквы **M / I / N / A** в `My Intelligent Navigation Assistant` автоматически используют **тот же исходный цвет**, извлечённый из оригинального CSS-правила `.mina-name`. Мы не угадываем оттенок и не задаём второй брендовый цвет.
- Все остальные буквы строки остаются приглушённым blue-gray `#8A9AA9`.
- Навигационные всплывающие карточки, чат, календарь, reminders, memory, voice, Family Hub и LLM не затронуты.

## Установка поверх v2.15.1

Останови Streamlit клавишами `Control + C`, скачай ZIP в `~/Downloads`, затем:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
mkdir -p .mina_backup_before_v2152
cp -p streamlit_app.py mina_welcome_polish_v2151.css .mina_backup_before_v2152/
unzip -o ~/Downloads/MINA_v2_15_2_Restore_Original_Brand_Accent.zip -d .
python -m unittest -q test_mina_welcome_color_v2152.py test_mina_welcome_polish_v2151.py test_mina_v215.py
python -m streamlit run streamlit_app.py
```

## Быстрая проверка

1. Перейди на главную страницу и проверь, что **MINA** снова имеет прежний (до v2.15.1) оттенок, не navy.
2. Сравни буквы **M I N A** второй строки с **MINA** в заголовке: оттенок совпадает.
3. Остальные буквы второй строки остаются мягкими и светлыми. Нажми `How it works` или `Features`: карточки по-прежнему открываются рядом с кнопками.
4. `Get started` открывает чат.

## Замечания по проверке

Локально пройдено **36/36** выбранных тестов (включая статические проверки v2.15 и v2.15.1) и Python compile. Визуальный результат в браузере на твоём Mac ещё нужно подтвердить: в окружении создания патча нет оригинальных CSS-файлов твоего приложения, поэтому исходный оттенок не подбирался вручную.

## Откат

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
cp -p .mina_backup_before_v2152/streamlit_app.py .
cp -p .mina_backup_before_v2152/mina_welcome_polish_v2151.css .
python -m streamlit run streamlit_app.py
```
