# MINA v2.14.2 — Remember public geocoding permission (RU)

## Что меняется
- Разрешение из Settings → Family Hub → “Allow public geocoding ...” теперь запоминается между перезапусками MINA и при замене файлов приложения.
- На новой установке по умолчанию **OFF**. После установки один раз включите галочку вручную. Далее она останется ON, пока вы сами её не выключите.
- Выключение тоже запоминается. Согласие можно отозвать через ту же галочку.
- Согласие хранится **локально на этом Mac** в `~/.mina/route_provider_consent.json` (только `version` и boolean `enabled`, без адресов или координат). Это файл вне папки кода, он не перезаписывается обычными обновлениями проекта.
- Включение галочки само по себе не вызывает геокодирование. При **запросе маршрута** адреса сохранённых мест могут передаваться US Census / Photon, а их координаты — HeiGIT / openrouteservice. Включая галочку, пользователь соглашается на эту передачу для своих сохранённых мест, включая Home/School. Отзыв согласия не удаляет прошлые обращения у сторонних сервисов.
- Неправильное/повреждённое содержимое файла согласия приводит к безопасному OFF и предупреждению.

## Установка ТОЛЬКО поверх MINA v2.14.1
1. Остановите Streamlit: `Control + C` в Terminal.
2. Сохраните резервную копию приложения.
3. Распакуйте ZIP в папку проекта.

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
mkdir -p .mina_backup_before_v2142
cp -p streamlit_app.py .mina_backup_before_v2142/
unzip -o ~/Downloads/MINA_v2_14_2_Persistent_Geocoding_Consent.zip -d .
python -m unittest -q test_mina_geocoding_consent_v2142.py test_mina_cancel_lifecycle_v2141.py
python -m streamlit run streamlit_app.py
```

## Проверка на вашем Mac (ещё не выполнена)
1. Settings → Family Hub → **Allow public geocoding**: включите галочку один раз.
2. Остановите Streamlit полностью; запустите снова.
3. Откройте Settings и убедитесь, что галочка всё ещё **ON**.
4. Снимите галочку; перезапустите и проверьте, что она **OFF**.
5. Если нужно, включите обратно. Не требуется повторно сохранять адреса, Home Pin или shopping lists.

## Прозрачность тестирования
В среде сборки прошли 16/16 выбранных offline-тестов для нового consent helper и существующей логики Cancel. `py_compile` для двух изменённых Python-файлов успешен. Полный Streamlit E2E на пользовательском Mac и полный набор старых тестов в среде сборки **не проводились**.

## Откат
```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
cp -p .mina_backup_before_v2142/streamlit_app.py streamlit_app.py
```
При откате новые helper-файлы остаются неиспользованными. Файл `~/.mina/route_provider_consent.json` можно удалить вручную, если хотите удалить сохранённое разрешение; при следующем запуске v2.14.2 default снова будет OFF.
