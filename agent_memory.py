"""
Модуль для хранения истории сообщений агента

Этот модуль содержит класс AgentMemory, который помогает сохранять и управлять
историей разговоров с AI-агентом (например, GigaChat).
"""

import logging
from typing import List, Dict, Optional
from functools import wraps

# Настраиваем логирование для этого модуля
logger = logging.getLogger(__name__)


def log_memory_operation(operation_name: str):
    """
    Декоратор для логирования операций с памятью агента
    
    Декоратор - это специальная функция, которая "оборачивает" другую функцию,
    добавляя к ней дополнительное поведение (в нашем случае - логирование).
    
    Что делает этот декоратор:
    - Перед выполнением операции записывает в лог, что операция началась
    - После выполнения операции записывает результат (успех или ошибку)
    
    Args:
        operation_name: Название операции для логирования (например, "add_message")
    
    Пример использования:
        @log_memory_operation("add_message")
        def add_message(self, role, content):
            # код функции
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Логируем начало операции
            logger.debug(f"[AgentMemory] Начало операции: {operation_name}")
            
            try:
                # Выполняем саму функцию
                result = func(self, *args, **kwargs)
                
                # Если операция успешна, логируем успех
                logger.debug(f"[AgentMemory] Операция '{operation_name}' выполнена успешно")
                return result
            except Exception as e:
                # Если произошла ошибка, логируем её
                logger.error(f"[AgentMemory] Ошибка при выполнении '{operation_name}': {e}")
                raise  # Пробрасываем ошибку дальше
        
        return wrapper
    return decorator


class AgentMemory:
    """
    Класс для хранения и управления историей сообщений агента
    
    Что такое класс?
    Класс - это шаблон для создания объектов. Объект - это конкретный экземпляр класса.
    Например, если класс - это "чертеж автомобиля", то объект - это конкретный автомобиль.
    
    Что делает этот класс:
    - Хранит историю всех сообщений в разговоре с агентом
    - Позволяет добавлять новые сообщения
    - Позволяет получать последние N сообщений
    - Автоматически очищает историю при выходе из блока "with"
    
    Пример использования:
        # Создаем объект памяти
        memory = AgentMemory()
        
        # Добавляем сообщения
        memory.add_message("user", "Привет!")
        memory.add_message("assistant", "Здравствуйте!")
        
        # Получаем последние 2 сообщения
        last_messages = memory.get_last_messages(2)
        
        # Используем с автоматической очисткой
        with AgentMemory() as mem:
            mem.add_message("user", "Вопрос")
            # После выхода из блока "with" память автоматически очистится
    """
    
    def __init__(self, initial_messages: Optional[List[Dict[str, str]]] = None):
        """
        Конструктор класса - вызывается при создании нового объекта
        
        Что такое конструктор?
        Это специальный метод, который выполняется автоматически при создании объекта.
        Здесь мы инициализируем (настраиваем) наш объект.
        
        Args:
            initial_messages: Начальные сообщения для загрузки в память (опционально)
                             Если не указано, память будет пустой.
        
        Важно про default аргументы:
        Мы используем None вместо пустого списка [] для initial_messages.
        Почему? Потому что изменяемые объекты (списки, словари) в default аргументах
        - это плохая практика. Они создаются один раз и используются для всех вызовов,
        что может привести к неожиданному поведению.
        
        Пример ПЛОХОГО кода:
            def __init__(self, messages=[]):  # НЕ ДЕЛАЙТЕ ТАК!
                self.messages = messages
        
        Пример ХОРОШЕГО кода (наш случай):
            def __init__(self, initial_messages=None):
                if initial_messages is None:
                    self.messages = []
                else:
                    self.messages = initial_messages.copy()
        """
        # Если начальные сообщения не переданы, создаем пустой список
        if initial_messages is None:
            self.messages: List[Dict[str, str]] = []
        else:
            # Используем .copy() чтобы создать копию списка
            # Это важно, чтобы изменения в нашем объекте не влияли на исходный список
            self.messages = initial_messages.copy()
        
        logger.info(f"[AgentMemory] Создан новый объект памяти. Сообщений: {len(self.messages)}")
    
    @log_memory_operation("add_message")
    def add_message(self, role: str, content: str) -> None:
        """
        Добавляет новое сообщение в историю
        
        Что делает этот метод:
        Создает словарь с информацией о сообщении и добавляет его в конец списка.
        
        Args:
            role: Роль отправителя сообщения
                 - "user" - сообщение от пользователя
                 - "assistant" - ответ от AI-агента
                 - "system" - системное сообщение
            content: Текст сообщения
        
        Returns:
            None (ничего не возвращает)
        
        Пример:
            memory = AgentMemory()
            memory.add_message("user", "Как дела?")
            memory.add_message("assistant", "Хорошо, спасибо!")
        """
        # Проверяем, что role и content не пустые
        if not role or not content:
            raise ValueError("role и content не могут быть пустыми")
        
        # Создаем словарь с информацией о сообщении
        # Словарь - это структура данных, которая хранит пары "ключ: значение"
        message = {
            "role": role.strip(),      # Убираем лишние пробелы
            "content": content.strip()  # Убираем лишние пробелы
        }
        
        # Добавляем сообщение в конец списка
        self.messages.append(message)
        
        logger.debug(f"[AgentMemory] Добавлено сообщение: role={role}, длина={len(content)} символов")
    
    @log_memory_operation("get_last_messages")
    def get_last_messages(self, n: int) -> List[Dict[str, str]]:
        """
        Возвращает последние N сообщений из истории
        
        Что делает этот метод:
        Берет последние N сообщений из списка и возвращает их.
        Если запрошено больше сообщений, чем есть в истории, вернет все доступные.
        
        Args:
            n: Количество последних сообщений, которые нужно вернуть
        
        Returns:
            Список словарей с сообщениями (копия, чтобы изменения не влияли на оригинал)
        
        Пример:
            memory = AgentMemory()
            memory.add_message("user", "Сообщение 1")
            memory.add_message("user", "Сообщение 2")
            memory.add_message("user", "Сообщение 3")
            
            # Получаем последние 2 сообщения
            last_two = memory.get_last_messages(2)
            # Вернет: [{"role": "user", "content": "Сообщение 2"}, 
            #          {"role": "user", "content": "Сообщение 3"}]
        """
        # Проверяем, что n положительное число
        if n < 0:
            raise ValueError("n должно быть положительным числом")
        
        # Если запрошено 0 сообщений, возвращаем пустой список
        if n == 0:
            return []
        
        # Берем последние N сообщений
        # [:] создает копию списка, чтобы изменения не влияли на оригинал
        last_messages = self.messages[-n:] if n <= len(self.messages) else self.messages[:]
        
        logger.debug(f"[AgentMemory] Запрошено {n} сообщений, возвращено {len(last_messages)}")
        
        return last_messages.copy()  # Возвращаем копию для безопасности
    
    @log_memory_operation("clear")
    def clear(self) -> None:
        """
        Очищает всю историю сообщений
        
        Что делает этот метод:
        Удаляет все сообщения из памяти, оставляя её пустой.
        
        Returns:
            None
        
        Пример:
            memory = AgentMemory()
            memory.add_message("user", "Привет")
            memory.clear()  # Теперь память пуста
        """
        self.messages.clear()
        logger.info("[AgentMemory] История сообщений очищена")
    
    def __enter__(self):
        """
        Метод для входа в контекстный менеджер (блок "with")
        
        Что такое контекстный менеджер?
        Это специальный объект, который можно использовать с ключевым словом "with".
        Он автоматически выполняет код при входе в блок и при выходе из него.
        
        Этот метод вызывается автоматически при входе в блок "with AgentMemory() as ..."
        
        Returns:
            self (возвращает сам объект)
        """
        logger.debug("[AgentMemory] Вход в контекстный менеджер")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Метод для выхода из контекстного менеджера (блок "with")
        
        Этот метод вызывается автоматически при выходе из блока "with".
        Здесь мы автоматически очищаем память.
        
        Args:
            exc_type: Тип исключения (если оно произошло), иначе None
            exc_val: Значение исключения (если оно произошло), иначе None
            exc_tb: Трассировка исключения (если оно произошло), иначе None
        
        Returns:
            False (означает, что исключения не обрабатываются здесь, они пробрасываются дальше)
        """
        logger.debug("[AgentMemory] Выход из контекстного менеджера, очистка памяти")
        self.clear()
        return False  # Не обрабатываем исключения здесь
    
    def __len__(self) -> int:
        """
        Возвращает количество сообщений в памяти
        
        Этот метод позволяет использовать функцию len() с объектом AgentMemory.
        
        Пример:
            memory = AgentMemory()
            memory.add_message("user", "Привет")
            print(len(memory))  # Выведет: 1
        
        Returns:
            Количество сообщений в памяти
        """
        return len(self.messages)
    
    def __repr__(self) -> str:
        """
        Возвращает строковое представление объекта для отладки
        
        Этот метод вызывается при использовании функции repr() или print().
        Помогает понять, что находится в объекте.
        
        Returns:
            Строка с информацией об объекте
        """
        return f"AgentMemory(messages={len(self.messages)})"


# Пример использования класса (для тестирования)
if __name__ == "__main__":
    # Настраиваем логирование для примера
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("Пример 1: Базовое использование")
    print("=" * 60)
    
    # Создаем объект памяти
    memory = AgentMemory()
    
    # Добавляем сообщения
    memory.add_message("user", "Привет! Как дела?")
    memory.add_message("assistant", "Здравствуйте! У меня всё отлично, спасибо!")
    memory.add_message("user", "Расскажи о погоде")
    
    # Получаем последние 2 сообщения
    last_messages = memory.get_last_messages(2)
    print(f"\nПоследние 2 сообщения:")
    for msg in last_messages:
        print(f"  {msg['role']}: {msg['content']}")
    
    print(f"\nВсего сообщений в памяти: {len(memory)}")
    
    print("\n" + "=" * 60)
    print("Пример 2: Использование с контекстным менеджером (with)")
    print("=" * 60)
    
    # Используем память в блоке "with"
    # После выхода из блока память автоматически очистится
    with AgentMemory() as mem:
        mem.add_message("user", "Вопрос 1")
        mem.add_message("assistant", "Ответ 1")
        mem.add_message("user", "Вопрос 2")
        
        print(f"\nСообщений в памяти (внутри блока with): {len(mem)}")
        print("Последние сообщения:")
        for msg in mem.get_last_messages(3):
            print(f"  {msg['role']}: {msg['content']}")
    
    # После выхода из блока "with" память очищена
    print(f"\nСообщений в памяти (после выхода из блока with): {len(mem)}")
    
    print("\n" + "=" * 60)
    print("Пример 3: Создание с начальными сообщениями")
    print("=" * 60)
    
    # Создаем память с начальными сообщениями
    initial_messages = [
        {"role": "system", "content": "Ты полезный помощник"},
        {"role": "user", "content": "Привет"}
    ]
    
    memory_with_init = AgentMemory(initial_messages=initial_messages)
    print(f"Сообщений в памяти: {len(memory_with_init)}")
    memory_with_init.add_message("assistant", "Здравствуйте!")
    print(f"Сообщений после добавления: {len(memory_with_init)}")
