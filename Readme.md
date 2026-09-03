# Дипломная работа курса "Python-разработчик"

## API интернет магазина
Backend-приложение интернет-магазина, разработанное на Django и Django REST Framework.

Приложение предоставляет REST API для:

- регистрации и авторизации пользователей;
- подтверждения электронной почты;
- работы с категориями товаров;
- просмотра магазинов и товаров;
- работы с корзиной;
- управления контактными данными пользователя;
- оформления заказов;
- просмотра заказов;
- импорта каталога магазина из YAML-файла(локально и по url);
- фонового выполнения импорта данных.

Проект полностью запускается в Docker и использует Nginx в качестве внешней точки входа.

## Стек
- Python 3
- Django 
- Django Rest Framework
- Nginx
- Redis
- PostgreSQL
- Celery
- Docker, Docker Compose
- Pytest

## Запуск проекта

### Требования

#### Для запуска проекта необходимо установить:

- Docker
- Docker Compose

#### Проверить установку можно командами:

- `docker --version`
- `docker compose version`
### Запуск

- Клонировать репозиторий:

- Создать файл .env с необходимыми переменными окружения(их можно посмотреть в .env.example).

- После этого запустить контейнеры:

  - `docker compose up -d --build`

- Проверить состояние контейнеров:

  - `docker compose ps`

### После успешного запуска API доступно по адресу:

`http://localhost:80`

### Миграции базы данных

#### Для применения миграций:

- `docker compose exec web python manage.py migrate`

Если название Django-контейнера отличается от web, необходимо использовать соответствующее имя сервиса из docker-compose.yml.


### Основные API endpoints:

| Метод |	Endpoint | Назначение |
| ----------- | ----------- | ----------- |
| POST	 | /api/v1/user/register|	Регистрация пользователя
|POST	|/api/v1/user/register/confirm|	Подтверждение регистрации
|POST	|/api/v1/user/login|	Авторизация
|GET	|/api/v1/user/details|	Данные пользователя
|POST	|/api/v1/user/details|	Изменение данных пользователя
|GET	|/api/v1/categories|	Список категорий
|GET|	/api/v1/shops|	Список магазинов
|GET|	/api/v1/products|	Список товаров|
|GET	|/api/v1/basket|	Просмотр корзины
|POST|	/api/v1/basket|	Добавление товаров в корзину
|PUT	|/api/v1/basket|	Изменение количества товара
|DELETE|	/api/v1/basket|	Удаление товара из корзины
|GET	|/api/v1/user/contact|	Список контактов
|POST	|/api/v1/user/contact|	Добавление контакта
|PUT	|/api/v1/user/contact|	Изменение контакта
|DELETE|	/api/v1/user/contact|	Удаление контакта
|GET	|/api/v1/order|	Список заказов
|POST|	/api/v1/order|	Оформление заказа
|GET	|/api/v1/partner/state|	Получение состояния магазина
|POST|	/api/v1/partner/state	|Изменение состояния магазина
|POST|	/api/v1/partner/update|	Запуск импорта каталога
|GET|	/api/v1/partner/orders	|Заказы магазина

#### Для защищённых endpoint необходимо передавать токен авторизации:

Authorization: Token <TOKEN>

#### Авторизация

Для авторизации необходимо отправить запрос:

`POST /api/v1/user/login`

Пример тела запроса:


{

    "email": "user@example.com",
    "password": "password"
}

В случае успешной авторизации API возвращает токен:


{

    "status": "success",
    "data": {
        "token": "<TOKEN>",
        "user": {}
    }
}

Полученный токен используется для дальнейших запросов:

`Authorization: Token <TOKEN>`

#### Импорт каталога магазина

Для пользователя типа shop доступен импорт каталога магазина из YAML-файла.

Endpoint:

`POST /api/v1/partner/update`

Пример:

{

    "url": "https://raw.githubusercontent.com/netology-code/python-final-diplom/master/data/shop1.yaml"
}

#### Импорт выполняется в фоновом режиме с использованием Celery.

В ответ API возвращает идентификатор фоновой задачи:

{

    "status": "Accepted",
    "data": {
        "Task ID": "<TASK_ID>",
        "Message": "Импорт в фоновом режиме"
    }
}

#### Для выполнения импорта должны быть запущены Redis и Celery worker.

### Тестирование

Для API реализованы интеграционные тесты с использованием pytest и библиотеки requests.

Тесты выполняют реальные HTTP-запросы к приложению.

При запуске тестов с локальной машины API доступно через:

`http://localhost:80`

Запуск тестов:

`pytest tests.py -v`


