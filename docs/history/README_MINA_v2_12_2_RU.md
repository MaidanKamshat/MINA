# MINA v2.12.2 — Saved Places / Plan Date Compatibility Hotfix

## Подтверждённая причина

В предыдущей версии Voice Route Adapter в `streamlit_app.py` передавал в
`UISettings` `saved_places_file=''` и одновременно `plan_date=bridge.plan_date`.
Базовый backend v1.8 принимает `plan_date` только совместно с JSON-файлом
`Saved Places`; поэтому прекращал запрос с ошибкой
“Saved Places file and plan date must be supplied together.”
Заполненные в Family Hub адреса уже передаются отдельными `origin` и
`task_locations`, без второго Saved Places JSON.

## Исправление

- Во всех трёх путях подготовки `UISettings` дата передаётся backend
  только вместе с реально указанным Saved Places JSON.
- Для маршрута из локального Family Hub адреса, длительности, библиотечное
  время и departure time остаются типизированными параметрами.
- Дата из запроса **по-прежнему распознаётся** как 2026-11-23, остаётся в
  оригинальном тексте запроса и диагностическом trace, но НЕ применяется
  backend-проверкой окон v1.8, которая требует отдельного совместимого JSON.
  Не выдавайте часы работы, доступность или поездку за проверенные.
- Сохранение списков, календарь, UI/CSS и другие функции не меняются.

## Установка на Mac

Останови работающий Streamlit: Control+C в Terminal.

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_backup_v2121.py
cp mina_route_bridge_v212.py mina_route_bridge_backup_v2121.py
unzip -o ~/Downloads/MINA_v2_12_2_Saved_Places_Date_Fix.zip -d .
python -m unittest -v test_mina_saved_places_pair_v2122.py test_mina_route_dispatch_v2121.py test_mina_trip_voice_v212.py
python -m streamlit run streamlit_app.py
```

ZIP НЕ удаляет и НЕ заменяет `local_data/`, OAuth credentials, .env или списки.
Предполагается, что файлы версии v2.12.1 (`mina_trip_voice_v212.py` и остальной backend) уже установлены. Архив заменяет только два файла и добавляет новый тест и README.

## Проверка

Введи тот же запрос про Monday, November 23, 2026, library, Costco и pickup.
Раскрой How MINA decided. Ошибка про пару Saved Places/date должна исчезнуть.
Это не гарантия, что реальный HeiGIT роут или полный план пройдёт: если
появится следующая ошибка Coordinator/Critic, нужны status + trace без адресов.

Ни один реальный private home address или сохранённый файл не копировался
в этот ZIP. Offline tests не являются подтверждением live-работы на Mac.
