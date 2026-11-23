# MINA v2.12.3 — адреса Family Hub → координаты → Route Planner

**Проблема:** после v2.12.2 `route_voice_adapter: user_constraints_applied` и
`coordinator: planning/complex`, но `live_planning: needs_clarification,
reason_type: LocationRequired`. Адреса из Family Hub проходят проверку
наличия, но backend не может уверенно получить географические точки.

**Исправление (подлежит проверке на Mac):** добавлен preflight геокодирования
в `mina_route_geocode_v2123.py`. После отдельного разрешения в Settings →
Family Hub программа принимает уже сохранённые адреса дома, библиотеки,
Costco и школы, проверяет каждый адрес через U.S. Census Geocoder, затем,
если нужно, Photon (OSM), сверяет номер дома, название улицы и ZIP и передаёт
в backend координаты `longitude,latitude` вместо адресных строк. Никаких
«примерных» совпадений и автоматической подмены Costco на Target.

**Конфиденциальность:** чекбокс теперь явно разрешает отправку сохранённых
адресов публичным геокодерам (Census/Photon), а координат — HeiGIT. Без
разрешения обработка останавливается, сервисы не вызываются. Домашний адрес,
координаты и полный текст запроса не включаются в диагностический trace.
Geo-запросы происходят только при запуске планирования, не сохраняются
в кэше MINA или в новый файл. Провайдеры получают данные для обработки.

**Отказы:** если внешние сервисы недоступны, или адрес не совпадает точно,
MINA сообщает, какая именно точка (home / library / shopping stop / school)
не подтверждена. Надёжность geocoding не гарантирована: новые здания,
несовпадения по ZIP и неполные адреса могут быть отклонены, даже если адрес
существует. Это безопаснее, чем построить маршрут к неверной школе.

**Что патч не делает:** не подтверждает часы библиотеки/магазина, школьные
правила, будущую дорожную обстановку, и не вводит backend-проверку окон
`plan_date` из v1.8. Дата из текста запроса остаётся в trace и сообщении,
но прежний paired Saved Places JSON для сложных окон не создаётся.

## Установка

Останови Streamlit `Control+C`, затем:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_backup_v2122.py
unzip -o ~/Downloads/MINA_v2_12_3_Geocoding_Preflight_Fix.zip -d .
python -m unittest -q test_mina_route_geocode_v2123.py test_mina_saved_places_pair_v2122.py test_mina_route_dispatch_v2121.py test_mina_trip_voice_v212.py
python -m streamlit run streamlit_app.py
```

В Settings → Family Hub включи **Allow public geocoding (US Census / Photon)
and HeiGIT routing for saved addresses**. Повтори тот же план.
`How MINA decided` должен показывать `geocoding: matched_all_requested_stops`
или специальное `route_geocode_preflight: unresolved_saved_location` с
названием только проблемной точки. При успешном маршруте проверь
все остановки, карту и pickup deadline. Offline-тесты не заменяют проверки
живых Census/Photon/HeiGIT на твоём Mac.

ZIP заменяет только `streamlit_app.py` и добавляет `mina_route_geocode_v2123.py`
и тест. Не удаляет `local_data/`, `.env`, OAuth или шопинг-листы.
