from telegram.ext import Application

from . import base_datos
from .administracion import register_administration_handlers


def register_publicity_handlers(application: Application):

    # Inicializar la base de datos independiente.
    base_datos.init()

    # Registrar los comandos administrativos.
    register_administration_handlers(application)