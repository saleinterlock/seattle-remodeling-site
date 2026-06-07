# Запуск сайта — 3 шага (15 минут)

## ШАГ 1 — Facebook Pixel (5 мин)

1. Открой `business.facebook.com` → Events Manager → **Create Pixel**
2. Назови "Seattle Remodeling" → скопируй Pixel ID (число типа `123456789012345`)
3. В файле `index.html` найди `PIXEL_ID_HERE` (2 места) → замени на свой Pixel ID
4. То же самое в файле `thank-you.html` (1 место)

## ШАГ 2 — GitHub (5 мин)

1. Открой `github.com` → Sign In или Create Account
2. Нажми **New Repository** → назови `seattle-remodeling-site` → Public → Create
3. На странице репозитория нажми **Add file → Upload files**
4. Перетащи папку `website` → **Commit changes**

## ШАГ 3 — Vercel (5 мин)

1. Открой `vercel.com` → Continue with GitHub
2. Нажми **Import** → выбери `seattle-remodeling-site`
3. Перед деплоем нажми **Environment Variables** → добавь:

| Key | Value |
|-----|-------|
| `ANTHROPIC_API_KEY` | твой ключ (из AIS-OS .env) |
| `TELEGRAM_BOT_TOKEN` | токен бота (из @BotFather) |
| `TELEGRAM_OWNER_ID` | `450406528` |
| `OWNER_PASSWORD` | придумай пароль (например: `PRO2026seattle`) |

4. Нажми **Deploy** → через 1 минуту сайт живой!

---

## URL-адреса после деплоя

| Страница | URL |
|----------|-----|
| Лендинг | `https://seattle-remodeling-site.vercel.app` |
| Панель хозяина | `https://...vercel.app/owner` |
| Страница спасибо | `https://...vercel.app/thank-you` |

---

## Что заменить в index.html

- `Seattle Pro Remodeling` → название компании клиента
- `(206) 555-0000` → реальный номер телефона
- `info@seattleproremodeling.com` → реальный email
- Фото в секции Gallery → реальные фото проектов
- Отзывы (Sarah M., James R., Linda P.) → реальные отзывы с Google
- `WA State License #XXXXXXXXX` → реальный номер лицензии

---

## Тест AI чата (локально)

Открой `index.html` прямо в браузере (Chrome). Форма и чат работают.
AI чат потребует Vercel deployment для ответов Claude.

Для тестирования чата без Vercel — открой `api/chat.py` и запусти:
```bash
pip install anthropic python-dotenv
```
Потом задеплой на Vercel — это займёт 1 минуту.
