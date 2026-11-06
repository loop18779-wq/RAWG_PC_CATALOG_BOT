
from MENU.menu_principal import register_main_menu_handlers

from importlib import import_module

english_router_module = import_module(
    "MENU.CURSOS DE IDIOMAS.INGLES.router"
)

register_english_menu_handlers = (
    english_router_module.register_english_menu_handlers
)


def register_menu_handlers(application):
    register_main_menu_handlers(application)
    register_english_menu_handlers(application)
