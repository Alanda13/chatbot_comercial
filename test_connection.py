import mssql_python

from src.database import get_connection

def test_database_connection():
    connection = None
    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT 1")
        result = cursor.fetchone()

        if result and result[0] == 1:
            print("CONEXÃO COM O BANCO REALIZADA COM SUCESSO!!")
        else:
            print("A CONEXÃO OCORREU, MAS O TESTE NÃO RETORNOU O RESULTADO ESPERADO.")

    except mssql_python.Error as error:
        print("ERRO AO CONECTAR AO BANCO DE DADOS!!!:")
        print(error)

    except ValueError as error:
        print("ERRO DE CONFIGURAÇÃO!!!:")
        print(error)

    finally:
        if connection is not None:
            connection.close()
            print("CONEXÃO ENCERRADA COM SUCESSO!!!")

if __name__ == "__main__":
    test_database_connection()