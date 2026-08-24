import os
import mssql_python
from dotenv import load_dotenv

load_dotenv() 

def get_connection():
    """
    Cria e retorna uma conexão com o banco Azure SQL.
    """
    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_DATABASE")
    username = os.getenv("DB_USERNAME")
    password = os.getenv("DB_PASSWORD")

    if not all([server, database, username, password]): 
        raise ValueError(
            "As variáveis DB_SERVER, DB_DATABASE, "
            "DB_USERNAME e DB_PASSWORD devem estar preenchidas no arquivo .env."
        )
    connection = mssql_python.connect(
        server=server,
        database=database,
        uid=username,
        pwd=password,
        encrypt="yes",
        timeout=30,
    )
    return connection