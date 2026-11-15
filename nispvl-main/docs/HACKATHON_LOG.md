# Журнал хакатона NASA Space Apps 2026 — «Агро-Севооборот»

Задача: Field Shift: Adapting Farms with NASA Data. Соревновательные дни: 14–15 ноября 2026.
Каждый коммит, сделанный в эти дни, начинается с `[hackathon]` — по ним можно отделить новое от прежнего.

## Что существовало до хакатона (по README.md)

| Область | Что было |
|---|---|
| Аккаунты и поля | регистрация, вход, демо-песочница `/demo`; поля на карте (рисование, GeoJSON/KML), история культур, почвенное обследование; изоляция по владельцу (чужое поле → 404) |
| Данные по полю | NASA POWER (климат), MODIS NDVI, SMAP (влажность почвы, нужен Earthdata), SoilGrids (почва); файловый кэш, демо-данные в `data/demo`, `OFFLINE=1` |
| Мониторинг и риски | помесячный климат и аномалии, NDVI, влажность SMAP, история сезонов, риски сезона, пригодность культур, слои карты |
| Планировщик | сравнение 2–4 севооборотов по почве, воде, доходу и риску на 3–5 лет, экономика, стресс-тест засухой, объяснения по шаблонам |
| Отчёты | PDF и XLSX на ru/kk/en |
| Качество | 109 тестов, аудит модели (`docs/MODEL_AUDIT.md`, `docs/audit/PARAMETERS.md`), все параметры модели в `backend/app/rules/*.yaml` |
| Демо без сети | `/demo` с двумя реальными полями (Шортанды, Костанай), `make offline-check` |

## Built during the hackathon (14–15 Nov 2026)

| Задача | Что сделано | Файлы | Коммит |
|---|---|---|---|
| 1. Проверка проекта | `make test` (109), `lint`, `build`, `offline-check` проходят; живой запрос для точки 52.3/68.5: POWER, SoilGrids — OK, MODIS — медленно, SMAP — не проверен (в контейнере нет токена и закрыт `urs.earthdata.nasa.gov`) | `docs/HACKATHON_LOG.md`, `docs/contracts/bare_soil.example.json` | ветка `hackathon/task1-log-and-contract` |
| 2. Каркас `/bare-soil` | эндпоинт по контракту, проверка владельца, период 2001…текущий год; числа пока `null`, `status: missing` | `backend/app/schemas.py`, `services/bare_soil.py`, `api/accounts.py`, `tests/test_bare_soil.py`, `docs/contracts/README.md`, `README.md` | ветка `hackathon/task2-bare-soil-endpoint` |
| 3. Пороги эрозии | `rules/erosion.yaml`: NDVI < 0,30 (нет зелёного покрова — открытая почва или стерня), ветер ≥ 5 м/с на 2 м по POWER `WS2M_MAX` (RWEQ), сухо — SMAP ниже влажности завядания 0–5 см (Chepil 1956), GWETTOP — порог по распределению SMAP для поля (Reichle & Koster 2004), снег — MOD13Q1 код 2 или POWER FRSNO ≥ 0,5 и SNODP ≥ 2,54 см; 12 источников в `sources.yaml`; загрузчик проверяет группы, диапазоны, высоту ветра; `make audit` показывает «Часы» при NDVI 0,25 и 0,30 | `backend/app/rules/erosion.yaml`, `rules/sources.yaml`, `model/rules.py`, `services/bare_soil.py`, `tests/test_rules.py`, `scripts/audit_model.py`, `docs/contracts/README.md`, `docs/LIMITATIONS.md` | ветка `hackathon/task3-erosion-rules` |
| 4. Расчёт «Часов голой почвы» | POWER: + `WS2M`, `WS10M`, `WS2M_MAX`, `WS10M_MAX`, `FRSNO`, `SNODP` (кэш v2), демо обоих полей обновлено живым запросом 14.11.2026. MODIS: источник `modis_shoulder` (DOY 81–113 и 289–305, окна ≤ 10 дат), счётчики `pixel_reliability` (снег 2 и облака 3 раздельно) и квантили NDVI у каждого композита. SMAP: источник `smap_season` (апрель–октябрь, кэш гранул общий с `smap`), иначе GWETTOP с порогом по SMAP. Расчёт: суточный NDVI (интерполяция ≤ 32 дней, не через снег), `exposure = joint_days / known_days`, `missing` с `missing_reason` вместо нуля, климатология, `top_months`, окна покровных культур по заморозкам POWER; 11 новых правил в `erosion.yaml`. Тесты: снег не бывает «без покрова», неизвестное условие не даёт опасного дня, пороги только из правил, офлайн-демо, новое поле запускает `modis_shoulder` | `backend/app/analytics/bare_soil.py`, `services/bare_soil.py`, `data_sources/{power,modis,smap,registry}.py`, `data_sources/sources.yaml`, `rules/erosion.yaml`, `rules/sources.yaml`, `model/rules.py`, `schemas.py`, `tests/test_bare_soil*.py`, `tests/fixtures/bare_soil/`, `scripts/{build_demo,offline_check,audit_model}.py`, `data/demo/**/power.json`, `docs/audit/`, `docs/contracts/`, `docs/LIMITATIONS.md`, локали | ветка `hackathon/task4-bare-soil-compute` |
| 4б. Данные и проверка на ноутбуке (15.11.2026) | MODIS сезон + межсезонье с квантилями NDVI для обоих полей; SMAP `smap_season` апрель–октябрь 2015–2026 (2 486 гранул на поле, 0 сбоев, ≈ 33 мин на оба поля). Исправлено: пустые значения в `.env` из `.env.example` (`DB_PATH=`) ломали SQLite (`Path("")` = `.`) — теперь «не задано» (`env_ignore_empty`); фикстура `test_api` всегда возвращает `OFFLINE`; тест на копию `.env.example`. Аудит: «Ждут MODIS межсезонья» и «По среднему NDVI» = 0; таблица GWETTOP/SMAP по месяцам; найдено сезонное смещение порога GWETTOP (не исправлено, `docs/MODEL_AUDIT.md` § 6). Python 3.14 на Mac: 165 тестов проходят, только предупреждение Starlette об `httpx` | `backend/app/config.py`, `tests/test_api.py`, `tests/test_config.py`, `data/demo/**/{modis,modis_shoulder,smap_season}.json`, `scripts/audit_model.py`, `docs/audit/`, `docs/MODEL_AUDIT.md` | ветка `hackathon/task4-bare-soil-compute` |
| 4в. Окна покровных культур только после уборки (15.11.2026) | Новое правило `cover_crop.harvest_end` по областям (01.10, `assumption`: рекомендации не найдены, опора — сводки об окончании уборки, `kz_harvest_reports`); окно начинается не раньше этой даты; при пустом списке — `cover_crop_note` (`reason`, `basis` ru/kk/en). Костанай: было 08.05–31.05 (весенний сев), стало «нет» — заморозок 29.09 до окончания уборки; Шортанды — «нет», как и было. Загрузчик требует дату для каждой области; `harvest_end` в `effective_thresholds`; `make offline-check` проверяет, что окна не раньше уборки | `rules/erosion.yaml`, `rules/sources.yaml`, `model/rules.py`, `analytics/bare_soil.py`, `services/bare_soil.py`, `api/accounts.py`, `schemas.py`, `tests/test_bare_soil.py`, `tests/test_rules.py`, `scripts/{audit_model,offline_check}.py`, `docs/contracts/`, `docs/audit/`, `docs/MODEL_AUDIT.md` § 6.5, `docs/LIMITATIONS.md` Д11 | ветка `hackathon/task4-bare-soil-compute` |
| 4г. Совет, если окна нет (15.11.2026) | `cover_crop_note.advice` (ru/kk/en): оставить стоящую стерню, не пахать осенью — стоящие остатки сильно снижают ветровую эрозию; `advice_scope: general_guidance` (не рекомендация для поля), источник `bilbro_fryrear_1994` со статусом как записан (только выдержка), казахский — на вычитку | `rules/erosion.yaml`, `model/rules.py`, `analytics/bare_soil.py`, `services/bare_soil.py`, `schemas.py`, тесты, `docs/contracts/` | ветка `hackathon/task4-bare-soil-compute` |
| 5. Дни без покрова в планировщике (15.11.2026) | Окна сева и уборки у каждой культуры в `crops.yaml` (пшеница — Казгидромет, прогноз сроков сева 2025 и созревания 2026, `agronomist_review`; остальные — `assumption`/`preliminary`: рекомендации НПЦ им. Бараева в контейнере недоступны), у пара `bare_whole_season`; `erosion.yaml` → `planner` (покров с конца окна сева до середины окна уборки, `model_design`). Загрузчик: окна у всех культур, сев раньше уборки, уборка зерновых не позже `cover_crop.harvest_end`. У каждого варианта `bare_days_per_year`, `exposure_index` и объект `bare_soil` (по годам, сезон, правила), в ответе `bare_soil_season`; климатология ветра и сухости — общий с «Часами» суточный ряд. В балл не входит. Демо Шортанды: пар 210 дн., пшеница 107, сценарий с паром 135 дн./год | `rules/{crops,erosion,sources}.yaml`, `model/rules.py`, `analytics/scenario_exposure.py`, `services/{bare_soil,comparison}.py`, `tests/test_scenario_exposure.py`, `scripts/offline_check.py`, `docs/contracts/README.md` | ветка `hackathon/task5-planner-bare-soil` |
| 5б. Отчёты и аудит (15.11.2026) | PDF (раздел 7) и XLSX (лист сравнения, расчёт по годам): дни без покрова в год и индекс эрозии, под таблицей — сезон, источники и статусы окон; старые анализы — «—». `make audit`: дни без покрова по сценариям обоих полей, вариант «а» (пятая оценка «эрозия», половина веса почвы) меняет лучший сценарий в 2 случаях из 10 (Шортанды: «влага», «риск»), чувствительность к границам покрова — 9 сочетаний. Рекомендация: пока не включать в балл (`MODEL_AUDIT.md` § 7.5) | `report/{pdf,xlsx}.py`, `locales/report.yaml`, `scripts/audit_model.py`, `docs/audit/`, `docs/MODEL_AUDIT.md` § 7, `docs/LIMITATIONS.md` Д12, `README.md` | ветка `hackathon/task5-planner-bare-soil` |

## Сделано: MODIS межсезонья и SMAP для демо-полей (на ноутбуке, 15.11.2026)

Загружено: `make demo ARGS="--only modis,modis_shoulder,smap_season"`; результат — `docs/MODEL_AUDIT.md`, раздел 6.
Медиана exposure (NDVI < 0,30, 2015–2025): Шортанды — октябрь 0,34, май 0,03, остальное 0; Костанай — ноябрь 0,47
(5 лет), май 0,29, октябрь 0,26, сентябрь 0,23.

Осталось:

- per-month GWETTOP calibration prepared on branch hackathon/gwettop-monthly, not merged pending stability check (bootstrap over years) (`MODEL_AUDIT.md` § 6.3);
- пересмотреть `cover_crop.min_median_exposure` по новым апрелю и октябрю;
- агроному: дата окончания уборки на поле и покровные культуры, успевающие до заморозка (`MODEL_AUDIT.md` § 6.5);
- заменить синтетические фикстуры настоящими ответами (`backend/tests/fixtures/bare_soil/README.md`);
- сверить NDVI Шортанды 2024–2026 после уборки с журналом поля;
- решить, включать ли индекс эрозии планировщика в балл (`MODEL_AUDIT.md` § 7.5); агроному — окна сева и уборки культур (кроме пшеницы источника нет), рекомендации НПЦ им. Бараева (`nasec.kz` закрыт сетевой политикой контейнера).

## To verify on full text

В контейнере хакатона полные тексты статей были недоступны (сайты издателей и репозиториев закрыты сетевой политикой), поэтому источники порогов
эрозии проверены **только по выдержкам из поисковой выдачи**. У каждого такого источника в `backend/app/rules/sources.yaml` стоит
note «Проверено только по выдержке, полный текст не прочитан», и ни одно правило на них не имеет `status: verified`.
После сверки по полному тексту: убрать эту пометку из note и, если значение применимо к Северному Казахстану, поднять `evidence`.

| Приоритет | Источник (id) | Что сверить | Где в правилах |
|---|---|---|---|
| 1 | RWEQ, Fryrear et al. 1998, Technical Bulletin No. 1 (`rweq_1998`) | порог 5 м/с именно на высоте 2 м и к какой скорости он относится (часовая, мгновенная); снежный покров > 25,4 мм как защитный | `erosive_wind.speed_ms`, `snow.power_snodp_min_cm` |
| 2 | Chepil 1956, SSSA Proc. 20:288–292 (`chepil_1956`) | эродируемость ≈ 0 при влажности завядания (15 атм) и почти без изменений ниже ~1/3 её | `dry_topsoil.smap_wilting_point_factor` |
| 3 | Sobrino et al. 2004, RSE 90:434–440 (`sobrino_2004`) | NDVI < 0,2 — открытая почва, > 0,5 — сплошная растительность | `bare_soil.ndvi_max` (range) |
| 4 | Lamb et al. 2022, Remote Sensing 14:6128 (`lamb_2022`) | выборка NDVI < 0,3 для сцен без заметной зелени | `bare_soil.ndvi_max` |
| 5 | Dvorakova et al. 2021, Remote Sensing 13:1791 (`dvorakova_2021`) | порог NDVI < 0,25 и точное название статьи | `bare_soil.ndvi_max` (range) |
| 6 | Reichle & Koster 2004, GRL 31 (`reichle_koster_2004`) | метод сопоставления распределений (CDF matching) | `dry_topsoil.gwettop_min_pairs` |
| 7 | Fécan et al. 1999, Ann. Geophys. 17:149–157 (`fecan_1999`) | коэффициенты w′ = 0,0014·глина² + 0,17·глина | note к `dry_topsoil.smap_wilting_point_factor` |
| 8 | Daughtry et al. 2004, RSE (`daughtry_residue`) | NDVI не связан с покрытием остатками; том и страницы | комментарий к `bare_soil` |
| 9 | Bilbro & Fryrear 1994, Agron. J. (`bilbro_fryrear_1994`) | снижение потерь почвы стоящей стерней; DOI | комментарий к `bare_soil` |
| 10 | GMAO MERRA-2 FAQ (`gmao_merra2_faq`) | SFMC = пористость × GWETTOP; SNODP — в заснеженной части ячейки | `snow.power_frsno_min`, комментарий к `dry_topsoil` |
| 11 | MOD13 User Guide C6.1 (`mod13_user_guide`) | таблица pixel_reliability: 2 — снег/лёд | `snow.modis_reliability_snow` |
| — | А. А. Зайцева (через ru-ecology.info), первоисточник не установлен | найти первоисточник: 6 м/с (лёгкие) и ≥ 10 м/с (тяжёлые почвы) на высоте флюгера, Северный Казахстан | только note к `erosive_wind.speed_ms` |
