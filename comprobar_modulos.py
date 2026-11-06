
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

TEST_DB = (
    ROOT
    / "backups"
    / "rawg_catalog_migracion_20261106_130404.db"
)

if not TEST_DB.exists():
    raise FileNotFoundError(TEST_DB)

os.environ["CATALOG_DB_PATH"] = str(TEST_DB)

print("1. Comprobando base de datos...")
import database_nueva
database_nueva.init()
print("OK")

print("\n2. Comprobando publicador...")
import publisher
print("OK")

print("\n3. Comprobando coordinador...")
import main
print("OK")

print("\n4. Comprobando estadísticas...")
print(database_nueva.stats())

print("\nTODOS LOS MÓDULOS SE HAN CARGADO CORRECTAMENTE.")
