<div align="center">

# 🔧 GOCAB 225 — API de gestion des pièces détachées

**Système de gestion des pièces détachées automobiles** — commandes, inventaire, approvisionnement et paiements fournisseurs.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00)](https://www.sqlalchemy.org/)
[![Licence](https://img.shields.io/badge/licence-propriétaire-lightgrey)](#-licence)

</div>

---

## 📋 À propos

GOCAB 225 est une application interne de gestion des pièces détachées automobiles, conçue pour le contexte d'un distributeur/gestionnaire de flotte. Elle couvre l'ensemble du cycle : du **catalogue de pièces** jusqu'au **suivi des paiements fournisseurs**, en passant par les **commandes**, l'**inventaire tournant** et les **besoins d'approvisionnement**.

Ce dépôt contient l'**API backend** (FastAPI). Le frontend (Next.js) est hébergé séparément.

---

## ✨ Fonctionnalités

| Module | Description |
|---|---|
| 🚗 **Catalogue** | Marques, modèles et pièces. Une pièce peut être compatible avec plusieurs modèles de **plusieurs marques** (relation many-to-many), ou universelle. |
| 🛒 **Commandes** | Enregistrement des commandes reçues, avec lignes, quantités et prix. |
| 📄 **Bons de commande** | Demandes d'approvisionnement à envoyer aux fournisseurs (cycle brouillon → envoyé → reçu), export **PDF** et **Excel**. |
| 📥 **Besoins d'approvisionnement** | Le magasinier signale les pièces manquantes ; l'admin transforme un besoin en un ou plusieurs bons (éclatement multi-fournisseurs). |
| 📦 **Inventaire** | Comptage tournant : les sorties sont calculées automatiquement entre deux comptages (stock précédent + entrées − compté). Anomalies signalées. |
| 💳 **Paiements** | Registre des demandes de paiement fournisseurs à transmettre au service finance, avec priorités et export Excel. |
| 📊 **Statistiques** | Volumes commandés par pièce, marque et modèle. |
| 👥 **Utilisateurs & rôles** | Authentification JWT et contrôle d'accès (RBAC) : `admin` et `magazinier`. |

---

## 🧱 Stack technique

- **FastAPI** (async) — framework web
- **PostgreSQL 16** — base de données
- **SQLAlchemy 2.0** (async / `asyncpg`) — ORM
- **Alembic** — migrations
- **Pydantic v2** — validation & schémas
- **python-jose** + **passlib[bcrypt]** — JWT & hachage des mots de passe
- **openpyxl** — exports Excel
- **reportlab** — génération PDF
- **Docker** / **docker-compose** — environnement de développement local

---

## 🏛️ Architecture

Le projet suit une **architecture en couches stricte**, chaque couche ayant une responsabilité unique :

```
Route (API)  →  Service (logique métier)  →  Repository (accès données)  →  SQLAlchemy  →  PostgreSQL
```

- **Route** — validation des entrées/sorties, gestion des permissions, aucune logique métier.
- **Service** — règles métier, orchestration, gestion des transactions (c'est lui qui `commit`).
- **Repository** — construction des requêtes, ne `commit` jamais.
- **Séparation des erreurs** — les erreurs d'intégrité base sont traduites en erreurs HTTP propres (404 / 409 / 422).

---

## 🚀 Démarrage rapide (local)

### Prérequis

- [Docker](https://www.docker.com/) & Docker Compose
- (ou) Python 3.11+ et un PostgreSQL local

### 1. Cloner le dépôt

```bash
git clone <url-du-depot>
cd gocab-225-backend
```

### 2. Configurer l'environnement

Copie le modèle et remplis les valeurs :

```bash
cp .env.example .env
```

Génère une clé secrète robuste pour le JWT :

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Colle le résultat dans `SECRET_KEY` (voir [Variables d'environnement](#-variables-denvironnement)).

### 3. Lancer avec Docker

```bash
docker compose up --build
```

L'API démarre sur **http://localhost:8000**. La documentation interactive (Swagger) est disponible sur **http://localhost:8000/docs**.

### 4. Créer le premier administrateur

Sans utilisateur, impossible de se connecter. Crée ton compte admin :

```bash
python -m scripts.create_admin --username dino --full-name "Dino" --role admin
```

Le mot de passe est demandé de façon masquée (jamais passé en argument).

---

## 🔐 Variables d'environnement

| Variable | Description | Exemple |
|---|---|---|
| `DATABASE_URL` | URL PostgreSQL (`postgresql://…`, normalisée en `asyncpg` côté app) | `postgresql://user:pass@db:5432/gocab` |
| `SECRET_KEY` | Clé de signature des JWT — **secrète, jamais commitée** | *(48 caractères aléatoires)* |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durée de validité d'un token | `720` |
| `JWT_ALGORITHM` | Algorithme de signature | `HS256` |
| `CORS_ORIGINS` | Origines autorisées (séparées par des virgules) | `https://gestion.gocab.ci` |

> ⚠️ Le fichier `.env` contient des secrets et **ne doit jamais** être commité. Il est ignoré par `.gitignore`. Seul `.env.example` (sans valeurs) est versionné.

---

## 🗃️ Migrations

Les migrations sont gérées par **Alembic**. Elles s'appliquent automatiquement au démarrage en production, et manuellement en local :

```bash
# Appliquer toutes les migrations
alembic upgrade head

# Créer une nouvelle migration après un changement de modèle
alembic revision -m "description du changement"
```

---

## 👤 Rôles & permissions

Deux rôles, aux périmètres cloisonnés :

| Module | 👑 Admin | 📦 Magasinier |
|---|:---:|:---:|
| Inventaire | ✅ Complet | ✅ Complet |
| Besoins d'approvisionnement | ✅ Tous | ✅ Les siens |
| Pièces / Marques / Modèles | ✅ Complet | 👁️ Lecture |
| Commandes | ✅ Complet | 👁️ Lecture *(sans prix)* |
| Bons de commande | ✅ Complet | ⛔ Aucun accès |
| Fournisseurs | ✅ Complet | ⛔ Aucun accès |
| Paiements | ✅ Complet | ⛔ Aucun accès |
| Statistiques | ✅ Complet | ⛔ Aucun accès |
| Utilisateurs | ✅ Complet | ⛔ Aucun accès |

> Le cloisonnement est appliqué **côté API** (pas seulement dans l'interface) : un magasinier ne reçoit jamais les montants financiers, même via un appel direct.

---

## 🧪 Tests

```bash
pytest -q
```

La suite couvre les règles métier de chaque module (cycles de vie, permissions, calculs d'inventaire, éclatement des besoins en bons, protections « dernier admin »…).

---

## ☁️ Déploiement

L'API est prévue pour un déploiement sur **Railway** (backend + PostgreSQL managé), le frontend sur **Vercel**.

Points clés en production :

- Les migrations s'exécutent au démarrage via `start.sh` (`alembic upgrade head` puis `uvicorn`).
- Le port est fourni par la plateforme via la variable `PORT`.
- `CORS_ORIGINS` doit contenir l'URL du frontend de production.
- `SECRET_KEY` de production **différente** de celle de développement.

---

## 📁 Structure du projet

```
app/
├── api/            # Routes (endpoints) + dépendances d'authentification
├── core/           # Config, sécurité (JWT/hash), exceptions, pagination
├── database/       # Session, base declarative
├── models/         # Modèles SQLAlchemy
├── repositories/   # Accès aux données
├── schemas/        # Schémas Pydantic (entrées/sorties)
└── services/       # Logique métier + exports (Excel/PDF)
alembic/            # Migrations
scripts/            # Scripts utilitaires (création d'admin…)
tests/              # Tests
```

---

## 📄 Licence

Projet **propriétaire** — GOCAB 225. Tous droits réservés. Usage interne uniquement.

---

<div align="center">
<sub>Construit avec soin pour GOCAB 225 · Abidjan, Côte d'Ivoire</sub>
</div>