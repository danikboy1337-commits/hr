import pandas as pd

df = pd.read_excel('questions.xlsx')

def distribute_questions(df, total_questions=20):
    """
    Распределяет вопросы по компетенциям на основе их весов
    
    Args:
        df: DataFrame с колонками 'competence' и 'weight'
        total_questions: общее количество вопросов (по умолчанию 20)
    
    Returns:
        DataFrame с добавленными колонками расчетов
    """
    
    # Создаем копию DataFrame
    result = df.copy()
    result.columns = [col.lower() for col in result.columns]
    
    # Шаг 1: cnt = weight * 20
    result['cnt'] = result['weight'] * total_questions
    
    # Шаг 2: int - целая часть (как ЦЕЛОЕ() в Excel)
    result['int'] = np.floor(result['cnt']).astype(int)
    
    # Шаг 3: top = 20 - сумма int
    sum_int = result['int'].sum()
    top = total_questions - sum_int
    
    # Шаг 4: diff = cnt - int (остаток)
    result['diff'] = result['cnt'] - result['int']
    
    # Шаг 5: prob = случайное число между 0 и diff
    result['prob'] = result['diff'].apply(lambda x: np.random.uniform(0, x))
    
    # Шаг 6: Сортируем по prob и берем топ компетенций
    result = result.sort_values('prob', ascending=False).reset_index(drop=True)
    
    # Шаг 7: gen - 1 для топ компетенций, 0 для остальных
    result['gen'] = 0
    result.loc[:top-1, 'gen'] = 1
    
    # Шаг 8: k = gen + int (финальное количество вопросов)
    result['k'] = result['gen'] + result['int']
    
    # Проверка: сумма k должна быть равна 20
    assert result['k'].sum() == total_questions, f"Ошибка: сумма k = {result['k'].sum()}, ожидалось {total_questions}"
    
    return result
