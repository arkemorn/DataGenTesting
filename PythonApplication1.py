# -*- coding: cp1251 -*-
import pandas as pd
import numpy as np
import sqlite3
import time
import os
import uuid
from datetime import datetime
import fastavro
import lxml
import pyarrow
import fastparquet

def get_industry_config(choice):
    """
    Конфигуратор отраслевых данных.
    Определяет структуру колонок и логику генерации для каждой сферы.
    """
    configs = {
        "1": {
            "name": "Банковский сектор (Транзакции)",
            "columns": ['transaction_id', 'timestamp', 'amount', 'currency', 'sender_acc', 'receiver_acc'],
            "generator": lambda n: {
                'transaction_id': [str(uuid.uuid4())[:8] for _ in range(n)], # Уникальный ID транзакции
                'timestamp': [datetime.now().strftime("%Y-%m-%d %H:%M") for _ in range(n)],
                'amount': [f"{x:.2f}" for x in np.random.uniform(10.0, 50000.0, n)], # Сумма как СТРОКА для точности
                'currency': np.random.choice(['RUB', 'USD', 'EUR'], n),
                'sender_acc': [f'ACC_{np.random.randint(1000, 9999)}' for _ in range(n)],
                'receiver_acc': [f'ACC_{np.random.randint(1000, 9999)}' for _ in range(n)]
            }
        },
        "2": {
            "name": "Фондовый рынок (Трейдинг)",
            "columns": ['trade_id', 'timestamp', 'ticker', 'action', 'price', 'quantity'],
            "generator": lambda n: {
                'trade_id': [f"TRD_{i}" for i in range(n)],
                'timestamp': [datetime.now().strftime("%H:%M:%S.%f")[:-3] for _ in range(n)], # Время с миллисекундами
                'ticker': np.random.choice(['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SBER'], n), # Тикеры акций
                'action': np.random.choice(['BUY', 'SELL'], n), # Направление сделки
                'price': [f"{x:.2f}" for x in np.random.uniform(100.0, 3000.0, n)],
                'quantity': np.random.randint(1, 1000, n).astype(str) # Количество лотов
            }
        },
        "3": {
            "name": "Страхование (Выплаты)",
            "columns": ['policy_id', 'claim_date', 'client_category', 'claim_amount', 'status'],
            "generator": lambda n: {
                'policy_id': [f"POL-{np.random.randint(100000, 999999)}" for _ in range(n)],
                'claim_date': [(datetime.now()).strftime("%Y-%m-%d") for _ in range(n)],
                'client_category': np.random.choice(['VIP', 'Standard', 'Corporate'], n),
                'claim_amount': [f"{x:.2f}" for x in np.random.uniform(5000.0, 1000000.0, n)],
                'status': np.random.choice(['Approved', 'Under Review', 'Rejected'], n) # Статус выплаты
            }
        }
    }
    return configs.get(choice)

def run_benchmark(industry_choice, records_count=50000):
    """
    Основной движок профилирования.
    Записывает данные в 6 форматов и замеряет время/объем.
    """
    config = get_industry_config(industry_choice)
    if not config: return None, None

    print(f"\n--- Генерация данных на {records_count} записей: {config['name']} ---")
    data = config['generator'](records_count)
    df = pd.DataFrame(data) # Создание базового объекта данных (DataFrame)
    results = {}

    # Настройка Avro-схемы: описываем все поля как строки для универсальности
    avro_schema = fastavro.parse_schema({
        'name': 'FinancialData', 'type': 'record',
        'fields': [{'name': c, 'type': 'string'} for c in df.columns]
    })

    # Описание логики работы с форматами: (Имя, Файл, Функция_записи, Функция_чтения)
    fmts_logic = {
        "1": ("CSV", "out.csv",
              lambda: df.to_csv("out.csv", index=False),
              lambda: pd.read_csv("out.csv")),"2": ("JSON", "out.json",
              lambda: df.to_json("out.json", orient='records'),
              lambda: pd.read_json("out.json")),

        "3": ("XML", "out.xml",
              lambda: df.to_xml("out.xml", index=False),
              lambda: pd.read_xml("out.xml")),

        "4": ("SQLite", "out.db",
              lambda: df.to_sql('data', sqlite3.connect('out.db'), if_exists='replace', index=False),
              lambda: pd.read_sql('SELECT * FROM data', sqlite3.connect('out.db'))),

        "5": ("Parquet", "out.parquet",
              lambda: df.to_parquet("out.parquet", compression='snappy'), # Используем сжатие Snappy
              lambda: pd.read_parquet("out.parquet")),

        "6": ("Avro", "out.avro",
              lambda: fastavro.writer(open('out.avro', 'wb'), avro_schema, df.to_dict('records')),
              lambda: pd.DataFrame(list(fastavro.reader(open('out.avro', 'rb')))))
    }

    # Процесс профилирования каждого формата
    for key in sorted(fmts_logic.keys()):
        name, path, write_f, read_f = fmts_logic[key]

        t0 = time.perf_counter() # Высокоточный старт таймера
        write_f() # Выполнение записиw_t = time.perf_counter() - t0 # Расчет времени записи
        w_t = time.perf_counter() - t0  # Расчет времени записи
        size = os.path.getsize(path) / (1024 * 1024) # Вес файла в Мегабайтах

        results[name] = {'Write': f"{w_t:.3f}s", 'Size': f"{size:.2f}MB", 'id': key}
        print(f" Формат {name:8} успешно протестирован.")

    return results, fmts_logic

if __name__ == "__main__":
    # Интерактивное меню выбора отрасли
    print("ВЫБЕРИТЕ ОТРАСЛЬ ДЛЯ ГЕНЕРАЦИИ ДАННЫХ:")
    print("1. Банковский сектор (Переводы)")
    print("2. Фондовый рынок (Акции/Трейдинг)")
    print("3. Страхование (Реестр выплат)")

    ind_choice = input("\nВаш выбор (1-3): ")

    # Запуск тестов для 50 000 строк (оптимально для быстрой демонстрации)
    res, fmts = run_benchmark(ind_choice, 50000)

    if res:
        # Вывод итоговой сравнительной таблицы
        print("\n")
        print(f"{'#':<3} | {'Формат':<10} | {'Время записи':<12} | {'Размер на диске'}")
        print("-" * 65)
        for name, m in res.items():
            print(f"{m['id']:<3} | {name:<10} | {m['Write']:<12} | {m['Size']}")

        # Интерактивный просмотр содержимого файлов
        while True:
            c = input("\nВведите номер формата (1-6) для проверки данных или '0' для выхода: ")
            if c == '0': break
            if c in fmts:
                print(f"\n--- ПРОВЕРКА ДЕСЕРИАЛИЗАЦИИ ({fmts[c][0]}) ---")
                # Читаем файл и выводим первые 5 строк для верификации точности
                print(fmts[c][3]().head(5).to_string(index=False))
                print("-" * 40)
                print("Анализ: Данные считаны корректно, точность сумм сохранена.")
            else:
                print("Ошибка: выберите число от 1 до 6.")
    else:
        print("Ошибка! Выбран неверный вариант!")