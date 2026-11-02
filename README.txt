BOT DE CATÁLOGO DE VIDEOJUEGOS PC — RAWG + TELEGRAM
===================================================

QUÉ HACE
- Busca videojuegos asociados a la plataforma PC en RAWG.
- Filtra resultados que incluyan la plataforma específica PC/Windows.
- Guarda el catálogo en SQLite y evita duplicados mediante el ID de RAWG.
- Publica hasta 20 juegos al día, entre las 09:00 y las 21:00 (Europe/Madrid),
  con un intervalo de 36 minutos.
- Publica imagen (cuando RAWG la proporciona) y una ficha detallada en texto.
- Muestra requisitos mínimos/recomendados solo cuando RAWG los proporciona;
  nunca inventa requisitos ausentes.
- Incluye atribución y enlace a la ficha de RAWG.
- Añade el botón «DESCARGAR JUEGO» solo si has asignado un enlace manual.
- Si se agotan los pendientes, pausa las publicaciones, no repite títulos,
  te envía un aviso privado y sigue revisando RAWG para descubrir novedades.
  Al detectar juegos nuevos, reanuda la cola automáticamente.
- Conserva el catálogo y el progreso en data/rawg_catalog.db.

ANTES DE EMPEZAR
1. Revoca el token de Telegram que compartiste anteriormente con @BotFather
   usando /revoke. Crea un token nuevo. No reutilices el token expuesto.
2. Crea/consigue una API key RAWG desde https://rawg.io/apidocs.
3. Elige un canal dedicado a videojuegos. El canal @thewholeguide que se probó
   anteriormente aparece con temática de curso de inglés; NO lo uses salvo que
   hayas confirmado expresamente que es el canal correcto.
4. Añade el bot como administrador del canal con permiso para publicar.

INSTALACIÓN EN WINDOWS 11 / PYCHARM
1. Descomprime esta carpeta y ábrela en PyCharm.
2. Abre Terminal en la carpeta del proyecto y ejecuta:

   py -3.12 -m venv .venv
   .venv\Scripts\activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt

CONFIGURACIÓN
1. Duplica .env.example y nombra la copia .env (sin extensión .txt).
2. Abre .env y rellena:
   TELEGRAM_BOT_TOKEN=TOKEN_NUEVO_DE_BOTFATHER
   TELEGRAM_CHANNEL_ID=@TU_CANAL_DE_VIDEOJUEGOS
   RAWG_API_KEY=TU_API_KEY_DE_RAWG
   ADMIN_SETUP_CODE=INVENTA_UN_CODIGO_LARGO_Y_PRIVADO
3. No compartas .env, ni tokens ni claves API.
4. Comprueba RAWG:
   python test_rawg.py
5. Ejecuta el bot:
   python main.py
   o haz doble clic en run.bat.

CONFIGURAR AVISOS PRIVADOS Y ENLACES
1. Busca tu bot en Telegram y pulsa Iniciar o envíale /start en privado.
   Envíale /start TU_CODIGO_SECRETO (el valor ADMIN_SETUP_CODE del .env). Así registra tu chat de forma privada; no compartas ese código.
2. Comandos privados:
   /estado
   /enlace ID_RAWG https://tu-enlace-de-descarga
3. Usa /pendientes para ver los IDs RAWG de los próximos juegos.
4. Asigna el enlace antes de que se publique el juego para que el botón aparezca.
   Si lo asignas después de publicar, no se edita la publicación ya enviada.

IMPORTANTE SOBRE EL CATÁLOGO
- RAWG no garantiza que cada juego tenga requisitos mínimos y recomendados.
- La API ofrece un catálogo sujeto a los datos, filtros, límites y condiciones de RAWG;
  no equivale a una lista exhaustiva de todos los juegos de PC existentes.
- Al alcanzar el final de la paginación inicial, el bot vuelve a consultar la primera
  página ordenada por novedades para detectar juegos recientes. Los IDs ya guardados
  no se vuelven a insertar ni publicar.
- La API gratuita, sus límites, atribución y condiciones pueden cambiar. Consulta
  https://rawg.io/apidocs y los términos actuales de RAWG antes de un uso comercial.
- Este proyecto no descarga ni aloja juegos: el botón abre el enlace que tú configures.

PARAR EL BOT
Pulsa CTRL+C en la terminal. La base de datos permanece guardada.
