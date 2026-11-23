# MINA v2.15.3 — Full-strength Teal Initials on Welcome Page

**Устанавливать поверх рабочей v2.15.2.** Это минимальный UI-only патч: заменяет **один CSS-файл** `mina_welcome_polish_v2151.css`. Не меняет ни приложение, ни backend, ни данные, ни память, ни Reminders.

## Что исправлено

- Слово **MINA** в заголовке «Welcome, I’m MINA» **не меняется** — остаётся его прежний насыщенный teal.
- Первые буквы **M / I / N / A** в «My Intelligent Navigation Assistant» отображаются с **полной насыщенностью** того же брендового оттенка. Дополнительно задан `-webkit-text-fill-color`, поскольку обычный `color` может не менять видимое отображение текста в Safari.
- На строке-подписи убрано родительское снижение непрозрачности (`opacity`) и фильтр (`filter`), которые могли осветлять и инициалы. Все остальные буквы по-прежнему имеют приглушённый blue-gray `#8A9AA9`.
- Popover-кнопки «How it works» и «Features» без изменений.

Цвет берётся из созданной v2.15.2 CSS-переменной `--mina-original-name-accent`. Резервный teal `#088F94` используется только когда соответствующее исходное CSS-значение не найдено.

## Установка

Останови Streamlit (`Control + C`). ZIP скачай в `~/Downloads`. Затем:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
mkdir -p .mina_backup_before_v2153
cp -p mina_welcome_polish_v2151.css .mina_backup_before_v2153/
unzip -o ~/Downloads/MINA_v2_15_3_Welcome_Full_Teal_Initials.zip -d .
python -m unittest -q test_mina_welcome_teal_v2153.py test_mina_welcome_color_v2152.py test_mina_welcome_polish_v2151.py test_mina_v215.py
python -m streamlit run streamlit_app.py
```

## Визуальная проверка

1. Сравни слово **MINA** в первой строке и отдельные **M, I, N, A** второй: цвет и насыщенность должны совпадать.
2. Прочие буквы второй строки — светло-приглушённые.
3. «How it works» и «Features» открывают popover; «Get started» ведёт в чат.

Локальные тесты не заменяют проверку браузера на Mac. Если Streamlit уже запущен, после замены CSS обязательно перезапусти сервер и обнови страницу Safari (`Cmd + R`).

## Откат

```bash
cp -p .mina_backup_before_v2153/mina_welcome_polish_v2151.css .
```
