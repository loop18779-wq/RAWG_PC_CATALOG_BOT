
import sqlite3
from pathlib import Path
from collections import Counter

# Base de datos independiente de inglés
DB_PATH = Path(__file__).resolve().parent / "data" / "ingles_catalog.db"

TOTAL_POR_NIVEL = 195
NIVELES = {
    1: "BÁSICO",
    2: "INTERMEDIO",
    3: "AVANZADO"
}

def main():
    print("=" * 65)
    print("       AUDITORÍA DEL CATÁLOGO DE VÍDEOS DE INGLÉS")
    print("=" * 65)

    if not DB_PATH.exists():
        print("ERROR: No se encuentra la base de datos:", DB_PATH)
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Comprobar integridad
    integrity = conn.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    print("\nINTEGRIDAD DE LA BASE DE DATOS:", integrity)

    # Leer las clases
    rows = conn.execute("""
        SELECT class_code, level, lesson_number,
               file_name, file_unique_id, file_id,
               storage_chat_id, storage_message_id
        FROM lessons
        ORDER BY level, lesson_number
    """).fetchall()

    print("\nREGISTROS ENCONTRADOS:", len(rows))

    registrados = set()
    codigos_repetidos = Counter()
    sin_file_id = []
    sin_unique_id = []
    sin_mensaje = []
    nombres_incorrectos = []

    for row in rows:
        code = row["class_code"]
        registrados.add(code)
        codigos_repetidos[code] += 1

        if not row["file_id"]:
            sin_file_id.append(code)

        if not row["file_unique_id"]:
            sin_unique_id.append(code)

        if row["storage_message_id"] is None:
            sin_mensaje.append(code)

        esperado = f"AI_{row['level']}_{row['lesson_number']:03d}.mp4"
        if row["file_name"] != esperado:
            nombres_incorrectos.append(
                (code, row["file_name"], esperado)
            )

    # Informe por nivel
    total_registrado = 0
    total_faltante = 0

    print("\n" + "=" * 65)
    print("DESGLOSE POR NIVEL")
    print("=" * 65)

    for nivel, nombre in NIVELES.items():
        codigos_nivel = {
            f"AI_{nivel}_{numero:03d}"
            for numero in range(1, TOTAL_POR_NIVEL + 1)
        }

        presentes = codigos_nivel.intersection(registrados)
        faltantes = sorted(codigos_nivel - registrados)

        total_registrado += len(presentes)
        total_faltante += len(faltantes)

        porcentaje = len(presentes) / TOTAL_POR_NIVEL * 100

        print(f"\n{nombre}")
        print("-" * 45)
        print(f"Registrados: {len(presentes)}/195")
        print(f"Faltantes:   {len(faltantes)}")
        print(f"Progreso:    {porcentaje:.2f}%")

        if faltantes:
            print("Clases que faltan:")
            print(", ".join(faltantes))

    # Registros fuera del catálogo esperado
    esperados = {
        f"AI_{nivel}_{numero:03d}"
        for nivel in NIVELES
        for numero in range(1, TOTAL_POR_NIVEL + 1)
    }

    inesperados = sorted(registrados - esperados)

    # Duplicados
    duplicados = [
        code for code, cantidad in codigos_repetidos.items()
        if cantidad > 1
    ]

    # Resumen
    print("\n" + "=" * 65)
    print("RESUMEN GENERAL")
    print("=" * 65)

    print("Total esperado:       585")
    print("Clases registradas:  ", total_registrado)
    print("Clases pendientes:   ", total_faltante)
    print("Códigos inesperados: ", len(inesperados))
    print("Códigos duplicados:  ", len(duplicados))
    print("Sin file_id:         ", len(sin_file_id))
    print("Sin file_unique_id:  ", len(sin_unique_id))
    print("Sin mensaje:         ", len(sin_mensaje))
    print("Nombres incorrectos: ", len(nombres_incorrectos))

    if inesperados:
        print("\nCÓDIGOS INESPERADOS:")
        print(", ".join(inesperados))

    if duplicados:
        print("\nCÓDIGOS DUPLICADOS:")
        print(", ".join(duplicados))

    if sin_file_id:
        print("\nSIN FILE_ID:")
        print(", ".join(sin_file_id))

    if sin_unique_id:
        print("\nSIN FILE_UNIQUE_ID:")
        print(", ".join(sin_unique_id))

    if sin_mensaje:
        print("\nSIN ID DE MENSAJE:")
        print(", ".join(sin_mensaje))

    if nombres_incorrectos:
        print("\nNOMBRES INCORRECTOS:")
        for code, actual, esperado in nombres_incorrectos:
            print(f"{code}: {actual} (esperado: {esperado})")

    print("\n" + "=" * 65)

    if (
        total_registrado == 585
        and total_faltante == 0
        and not inesperados
        and not duplicados
        and not sin_file_id
        and not sin_unique_id
        and not sin_mensaje
        and not nombres_incorrectos
    ):
        print("RESULTADO: LAS 585 CLASES ESTÁN COMPLETAS.")
    else:
        print("RESULTADO: HAY INCIDENCIAS QUE DEBEN REVISARSE.")

    print("=" * 65)

    conn.close()


if __name__ == "__main__":
    main()
