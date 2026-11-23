# MINA v2.12.4 — точка дома без неуверенного геокодирования

**Ситуация:** v2.12.3 остановилась на `route_geocode_preflight`: `home`,
`not_confidently_matched`. Внешние Census/Photon не подтвердили точный адрес.
Это не доказывает, что домашний адрес неправильный. Патч не ослабляет
безопасность и не угадывает местоположение.

**Исправление:** новый раздел Settings → Family Hub → **Private route pins**.
Пользователь один раз сам проверяет точное место на карте и сохраняет
координаты (широта, долгота) в локальном файле
`local_data/mina_private_route_pins.json`. В обычных запросах маршрутный
адаптер использует эту привязанную к исходному адресу точку; если сохранённый
адрес был изменён, старый pin перестаёт действовать. Пины также доступны
для школы, библиотеки, Costco, Target и Trader Joe’s на случай, если
другие адреса не распознаются. Остальные остановки продолжают
геокодироваться как раньше. Никаких координат в trace.

**Как сохранить Home:** Google Maps → найти свой дом → убедиться в правильной
точке → правый клик → What’s here? → копировать **latitude, longitude**
(например, `35.7, -78.8` — это только формат, НЕ координаты твоего дома).
В MINA: Settings → Family Hub → Private route pins → Home → вставить
координаты → **Save verified route pin locally**. Дальше прежний запрос.

**Безопасность:** координаты — персональные геоданные, не публикуй файл.
Сохраняются локально с правами 0600 и отпечатком адреса (без самого
адреса в файле). Координаты отправляются в HeiGIT только после согласия
на маршрутизацию, остальные адреса — в Census/Photon согласно текущему
чекбоксу. Списки, Google Calendar и ранее сохранённые адреса не меняются.

**Установка (после остановки Streamlit Control+C):**

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_backup_v2123.py
cp mina_route_geocode_v2123.py mina_route_geocode_v2123_backup.py
unzip -o ~/Downloads/MINA_v2_12_4_Private_Route_Pin_Fix.zip -d .
python -m unittest -q test_mina_route_pins_v2124.py test_mina_route_geocode_v2123.py test_mina_saved_places_pair_v2122.py test_mina_route_dispatch_v2121.py test_mina_trip_voice_v212.py
python -m streamlit run streamlit_app.py
```

ZIP заменяет 2 Python файла и добавляет `mina_route_pins_v2124.py` и тест.
Предполагается, что уже установлена v2.12.3. Не переносит и не удаляет
`local_data/`, `.env`, OAuth, Saved Places или shopping lists.

**Граница проверки:** unit-тесты используют фиктивные адреса/ответы. Живое
геокодирование остальных пунктов, HeiGIT и поведение на Mac надо проверить
отдельно. Реальный трафик/часы работы и автоматическая backend-проверка
временных окон на дату по-прежнему не гарантированы.
