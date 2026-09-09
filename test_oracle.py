from src.connection import get_connection

try:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM DUAL")
            result = cursor.fetchone()
            print("Conexão via módulo bem sucedida! Resultado:", result)

except Exception as e:
    print("Erro:", e)