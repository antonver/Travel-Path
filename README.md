# TravelPath Backend API

🌍 Backend API для мобильного приложения TravelPath — генератор персонализированных туристических маршрутов.

## 🚀 Production

**URL:** https://travel-path.onrender.com

**Документация:** https://travel-path.onrender.com/docs

## 📋 Возможности

- 🔐 **Аутентификация** — Firebase Auth (email/password)
- 🗺️ **Генерация маршрутов** — 3 варианта (Économique, Recommandé, Confort)
- 📍 **Google Places API** — поиск и информация о местах
- 📸 **Фото мест** — Google Photos + пользовательские фото (gRPC/REST)
- 💾 **Сохранение маршрутов** — Firestore
- ☁️ **Объектное хранилище** — Cloudflare R2 / AWS S3

## 🛠️ Технологии

- **FastAPI** — Python веб-фреймворк
- **Firebase Admin SDK** — аутентификация и Firestore
- **Google Maps Platform** — Places API, Directions API
- **MinIO/S3** — объектное хранилище для фото
- **gRPC** — синхронизация фото с партнёрским приложением
- **Docker** — контейнеризация
- **Render.com** — хостинг

## 🏃 Локальный запуск

### Требования
- Docker & Docker Compose
- Google Maps API Key
- Firebase Service Account Key

### Запуск

1. Клонируй репозиторий:
```bash
git clone https://github.com/antonver/Travel-Path.git
cd Travel-Path
```

2. Создай `.env` файл (скопируй из `.env.example`):
```bash
cp .env.example .env
# Заполни MAPS_API_KEY и другие переменные
```

3. Добавь `serviceAccountKey.json` (Firebase credentials)

4. Запусти:
```bash
docker-compose up --build
```

5. Открой http://localhost:8000/docs

## 📡 API Endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/auth/verify` | Верификация Firebase токена |
| POST | `/trips/generate` | Генерация маршрутов |
| POST | `/trips/save` | Сохранить маршрут |
| GET | `/trips/saved` | Получить сохранённые маршруты |
| GET | `/places/search` | Поиск мест |
| GET | `/places/details/{place_id}` | Детали места |
| POST | `/photos/upload` | Загрузка фото (REST) |
| GET | `/health` | Проверка состояния |

## 🔗 gRPC для партнёров

Для интеграции фото из партнёрского приложения используй `photo_service_for_partner.proto`:

```protobuf
service PhotoService {
    rpc UploadPlacePhoto(PlacePhotoRequest) returns (PlacePhotoResponse);
    rpc UploadPlacePhotoBatch(stream PlacePhotoRequest) returns (BatchPhotoResponse);
}
```

**gRPC Port:** 50051 (только для локальной разработки)

## 🌐 Деплой на Render

1. Подключи GitHub репозиторий к Render
2. Render автоматически найдёт `render.yaml`
3. Установи секреты в Dashboard:
   - `FIREBASE_CREDENTIALS_JSON` — JSON одной строкой
   - `MAPS_API_KEY` — Google Maps API ключ
   - `MINIO_ENDPOINT` — endpoint хранилища (без https://)
   - `MINIO_ROOT_USER` — Access Key
   - `MINIO_ROOT_PASSWORD` — Secret Key

## 📱 Android приложение

Репозиторий Android: отдельный проект TravelPath2

**BASE_URL в RetrofitClient.java:**
```java
private static final String BASE_URL = "https://travel-path.onrender.com/";
```

## 📄 Лицензия

MIT

