import pytest_asyncio

from tests.factory import ApiFactory


@pytest_asyncio.fixture
async def factory(client) -> ApiFactory:
    return ApiFactory(client)


@pytest_asyncio.fixture
async def catalog(factory) -> dict:
    """Jeu de données réutilisable : 2 marques, 2 modèles, 3 pièces, 2 fournisseurs.
    Aucune commande — chaque test crée les siennes selon son scénario."""
    bestune = await factory.brand("Bestune")
    chery = await factory.brand("Chery")
    t55 = await factory.model(bestune, "T55")
    tiggo = await factory.model(chery, "Tiggo 2")
    return {
        "bestune": bestune,
        "chery": chery,
        "t55": t55,
        "tiggo": tiggo,
        "sep": await factory.supplier("SEP-CI"),
        "hainan": await factory.supplier("Hainan Yabanqu"),
        "air": await factory.part(t55, "AIR-1", "Filtre à air"),
        "oil": await factory.part(t55, "OIL-1", "Filtre à huile"),
        "cond": await factory.part(tiggo, "COND-1", "Condenseur"),
    }