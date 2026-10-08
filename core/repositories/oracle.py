import os
import oracledb
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=True)

user = os.getenv("ORACLE_USER")
password = os.getenv("ORACLE_PASSWORD")
dsn = os.getenv("ORACLE_DSN")
lib_dir = os.getenv("ORACLE_LIB_DIR")

print(f"Usuário carregado: {user}")
print(f"Senha carregada: {'Sim' if password else 'Não'}")
print(f"DSN carregado: {'Sim' if dsn else 'Não'}")
print(f"Lib_dir carregado: {lib_dir}")

if lib_dir:
    oracledb.init_oracle_client(lib_dir=lib_dir)

def get_connection():
    if not user or not password or not dsn:
        raise ValueError("Credenciais não encontradas. Verifique o arquivo .env")
    return oracledb.connect(user=user, password=password, dsn=dsn)