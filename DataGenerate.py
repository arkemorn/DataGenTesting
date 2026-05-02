import os
import time
import uuid
import gc
import sqlite3
import tracemalloc
import datetime
import warnings
import pathlib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from tabulate import tabulate
import fastavro

# Отключаем всплывающие системные предупреждения, чтобы консоль была чистой
warnings.filterwarnings("ignore")

# --- БЛОК 1: ПОИСК И СИСТЕМНЫЕ ФУНКЦИИ ---

def open_folder_in_explorer():
    """Эта функция просто открывает папку, в которой лежит этот скрипт, в проводнике Windows"""
    try:
        # getcwd() получает путь к текущей папке, а startfile открывает её
        os.startfile(os.getcwd())
        print(f"\n[+] Папка с результатами открыта: {os.getcwd()}")
    except Exception as e:
        print(f"\n[-] Не удалось открыть папку автоматически: {e}")

def sqlite_point_lookup(db_path: pathlib.Path, transaction_id: str) -> pd.DataFrame:
    """Функция для быстрого поиска конкретной строки в базе данных SQLite по её ID"""
    connection = sqlite3.connect(db_path)
    try:
        # Создаем 'индекс' — это как оглавление в книге, позволяет искать мгновенно, не листая всё подряд
        connection.execute("CREATE INDEX IF NOT EXISTS idx_txid ON data(transaction_id)")
        # Выполняем SQL-запрос на поиск конкретного ID
        query = "SELECT * FROM data WHERE transaction_id = ?"
        result = pd.read_sql_query(query, connection, params=[transaction_id])
    finally:
        connection.close() # Всегда закрываем соединение с базой
    return result

def benchmark_call(callable_obj):
    """Специальная функция-'секундомер', которая замеряет время работы и потребление памяти"""
    gc.collect() # Очищаем старый мусор в памяти перед тестом
    tracemalloc.start() # Начинаем следить за расходом памяти
    start = time.perf_counter() # Засекаем точное время старта
    
    callable_obj() # Выполняем саму задачу (например, сохранение файла)
    
    elapsed = time.perf_counter() - start # Считаем, сколько секунд прошло
    _, peak_size = tracemalloc.get_traced_memory() # Узнаем, какой был пик потребления памяти
    tracemalloc.stop() # Перестаем следить за памятью
    return elapsed, peak_size / (1024 * 1024) # Возвращаем время и мегабайты

# --- БЛОК 2: ГЕНЕРАЦИЯ ДАННЫХ ---

def generate_extended_data(rows):
    """Создает таблицу со случайными финансовыми данными (транзакциями)"""
    np.random.seed(42) # Фиксируем случайность, чтобы при каждом запуске данные были одинаковыми
    base_time = pd.Timestamp("2025-01-01")
    
    # Генерируем таблицу (DataFrame): ID, время, сумма, валюта и статус
    return pd.DataFrame({
        "transaction_id": [str(uuid.uuid4())[:18] for _ in range(rows)],
        "event_time": base_time + pd.to_timedelta(np.random.randint(0, 31536000, size=rows), unit="s"),
        "amount_minor": np.random.randint(100, 5000000, size=rows),
        "currency": np.random.choice(["RUB", "USD", "EUR"], size=rows),
        "status": np.random.choice(["posted", "pending"], size=rows)
    })

# --- БЛОК 3: ОСНОВНОЙ ЦИКЛ ПРОГРАММЫ ---

def run_benchmark():
    # Приветствие и выбор режима
    print("ВЫБЕРИТЕ РЕЖИМ ГЕНЕРАЦИИ:")
    print("1. Банковский сектор (v1.0)")
    print("2. Фондовый рынок (v1.0)")
    print("3. Страхование (v1.0)")
    print("4. Расширенный финансовый датасет (v2.0)")
    
    ind_choice = input("\nВаш выбор: ")
    rows = 50000 # Количество строк для теста
    
    if ind_choice == "4":
        current_df = generate_extended_data(rows)
    else:
        # Если выбран 1, 2 или 3, всё равно используем расширенный набор для этого примера
        current_df = generate_extended_data(rows) 

    print(f"\nИдет генерация и запись файлов...")

    # Настройка схемы для формата Avro (описание структуры данных)
    avro_schema = fastavro.parse_schema({
        'name': 'Data', 'type': 'record',
        'fields': [{'name': c, 'type': 'string'} for c in current_df.columns]
    })

    # Список всех форматов, которые мы будем тестировать (Запись, Чтение, Имя файла)
    fmts_logic = {
        "1": ("CSV", lambda: current_df.to_csv("out.csv", index=False), lambda: pd.read_csv("out.csv"), "out.csv"),
        "2": ("JSON", lambda: current_df.to_json("out.json", orient='records', date_format='iso'), lambda: pd.read_json("out.json"), "out.json"),
        "3": ("XML", lambda: current_df.to_xml("out.xml", index=False), lambda: pd.read_xml("out.xml"), "out.xml"),
        "4": ("SQLite", lambda: current_df.to_sql('data', sqlite3.connect('out.db'), if_exists='replace', index=False), lambda: pd.read_sql('SELECT * FROM data', sqlite3.connect('out.db')), "out.db"),
        "5": ("Parquet", lambda: current_df.to_parquet("out.parquet"), lambda: pd.read_parquet("out.parquet"), "out.parquet"),
        "6": ("Avro", lambda: fastavro.writer(open('out.avro', 'wb'), avro_schema, current_df.astype(str).to_dict('records')), lambda: pd.DataFrame(list(fastavro.reader(open('out.avro', 'rb')))), "out.avro")
    }

    results_table = [] # Сюда сохраним результаты для итоговой таблицы
    chart_data = {'names': [], 'times': [], 'mems': [], 'sizes': []} # А сюда — для графиков

    # Проходим по каждому формату и запускаем тесты
    for key in sorted(fmts_logic.keys()):
        name, write_f, _, path = fmts_logic[key]
        t, m = benchmark_call(write_f) # Замеряем запись
        s = os.path.getsize(path) / (1024 * 1024) # Узнаем размер получившегося файла в МБ
        
        # Сохраняем данные для отчетов
        results_table.append([key, name, f"{t:.3f}s", f"{m:.2f} MB", f"{s:.2f} MB"])
        chart_data['names'].append(name)
        chart_data['times'].append(t)
        chart_data['mems'].append(m)
        chart_data['sizes'].append(s)

    # Печатаем красивую итоговую таблицу в консоли
    print("\n" + tabulate(results_table, headers=["#", "Формат", "Время", "Память", "Размер"], tablefmt="grid"))

    # ИНТЕРАКТИВНОЕ МЕНЮ: работает пока пользователь не введет 0
    while True:
        print("\n--- ДОСТУПНЫЕ ДЕЙСТВИЯ ---")
        print("1-6: Просмотр первых строк файла")
        print("7:   Поиск транзакции по ID (только для SQLite)")
        print("0:   Выйти и ПОСТРОИТЬ ГРАФИКИ")
        
        c = input("\nВаш выбор: ")
        
        if c == '0': 
            break # Выход из цикла для постройки графиков
            
        if c == '7':
            # Показываем пользователю примеры ID из базы, чтобы было что искать
            examples = current_df['transaction_id'].head(3).values
            print(f"\n[ИНСТРУКЦИЯ] Чтобы найти запись, введите ID транзакции.")
            print(f"Примеры ID из текущей базы для теста:")
            for ex in examples: print(f"  > {ex}")
            
            target_id = input("\nВведите ID для поиска (или Enter для примера): ")
            if not target_id: target_id = examples[0]
            
            print(f"\n[!] Поиск в out.db...")
            start_search = time.perf_counter()
            # Запускаем нашу функцию поиска в SQLite
            search_res = sqlite_point_lookup(pathlib.Path("out.db"), target_id)
            search_time = time.perf_counter() - start_search
            
            if not search_res.empty:
                print(tabulate(search_res, headers='keys', tablefmt='psql', showindex=False))
                print(f"Найдено мгновенно за {search_time:.5f} сек")
            else:
                print("Запись с таким ID не найдена.")
            
        elif c in fmts_logic:
            # Читаем файл и показываем первые 5 строк
            name, _, read_f, _ = fmts_logic[c]
            print(f"\n--- ПРОВЕРКА ДАННЫХ: {name} ---")
            print(tabulate(read_f().head(5), headers='keys', tablefmt='psql', showindex=False))

    # БЛОК ГРАФИКОВ: отрисовывается в самом конце
    print("\n[!] Подготовка графиков...")
    fig, axes = plt.subplots(1, 3, figsize=(16, 5)) # Создаем окно с 3-мя графиками
    fig.suptitle('Сравнение форматов', fontsize=14)

    # 1 график: Время
    axes[0].bar(chart_data['names'], chart_data['times'], color='skyblue')
    axes[0].set_title('Скорость записи (сек)')
    
    # 2 график: Оперативная память
    axes[1].bar(chart_data['names'], chart_data['mems'], color='salmon')
    axes[1].set_title('Пиковая память (МБ)')

    # 3 график: Вес файлов
    axes[2].bar(chart_data['names'], chart_data['sizes'], color='lightgreen')
    axes[2].set_title('Размер файла (МБ)')

    plt.tight_layout() # Автоматически подравниваем отступы
    plt.savefig('benchmark_results.png') # Сохраняем картинку
    print(f"График сохранен как 'benchmark_results.png'")
    
    # Открываем папку и показываем график на весь экран
    open_folder_in_explorer()

    manager = plt.get_current_fig_manager()
    try:
        manager.window.state('zoomed') # Для Windows: развернуть на весь экран
    except:
        try:
            manager.full_screen_toggle() # Для других систем
        except:
            pass
            
    plt.show() # Показываем само окно с графиками

# Точка входа: запускаем главную функцию
if __name__ == "__main__":
    run_benchmark()
