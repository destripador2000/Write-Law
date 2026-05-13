# Backend Developer Persona - DavidZuniga Style Guide

Este documento define las reglas de ingeniería backend que deben seguirse para replicar exactamente mi estilo de desarrollo. Cada instrucción está respaldada por código real extraído del proyecto.

---

## 1. Stack Tecnológico y Configuración

### Framework y ORM
- **FastAPI** como framework principal
- **SQLAlchemy 2.0+** con soporte asíncrono completo
- **Pydantic v2** para validación de esquemas
- **PostgreSQL** en producción, **SQLite en RAM** (aiosqlite) para testing

### Configuración del Núcleo de la App

**Inicialización de FastAPI en `app/main.py`:**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.models import *

app = FastAPI(title=settings.app_name)

origins = [
    settings.url_localhost_frontend,
    settings.url_alternativa_frontend,
    settings.url_frontend_produccion
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Configuración de Base de Datos Asíncrona en `app/core/database.py`:**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.base import Base

SQLALCHEMY_DATABASE_URL = settings.database_url

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,
    pool_pre_ping=True
)

SessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_db():
    async with SessionLocal() as session:
        yield session
```

**Settings con Pydantic en `app/core/config.py`:**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str
    admin_email: str
    database_url: str
    database_ram_url: str
    url_localhost_frontend: str
    url_alternativa_frontend: str
    url_frontend_produccion: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

settings = Settings()

def get_settings():
    return settings
```

---

## 2. Arquitectura y Estructura

### Estructura de Proyecto

```
backend/
├── app/
│   ├── main.py                           # FastAPI app + registro de routers
│   ├── core/
│   │   ├── config.py                     # Settings (Pydantic)
│   │   └── database.py                   # Async engine + get_db
│   ├── api/
│   │   └── routes/
│   │       ├── rt_verbs.py              # Prefijo rt_ para rutas
│   │       ├── rt_vocabularies.py
│   │       └── ...
│   ├── models/
│   │   ├── base.py                      # DeclarativeBase
│   │   ├── md_Verbs.py                  # Prefijo md_ para modelos
│   │   ├── md_Vocabulary.py
│   │   ├── md_Pages.py
│   │   └── ...
│   └── schemas/
│       ├── sch_verb.py                  # Prefijo sch_ para schemas
│       ├── sch_vocabulary.py
│       └── ...
├── test/
│   ├── conftest.py                      # Fixtures (BD en RAM)
│   ├── test_verb.py
│   └── pytest.ini
└── alembic/                             # Migraciones
```

### Separación de Responsabilidades

**Modelo SQLAlchemy (`app/models/md_Vocabulary.py`):**

```python
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey
from typing import TYPE_CHECKING
from .base import Base

if TYPE_CHECKING:
    from .md_Pages import Page

class Vocabulary(Base):
    __tablename__ = "vocabularies"

    id: Mapped[int] = mapped_column(primary_key=True)
    pages_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    word: Mapped[str] = mapped_column(String(30))
    meaning: Mapped[str] = mapped_column(String(35))
    page: Mapped["Page"] = relationship(back_populates="vocabularies")
```

**Schema Pydantic (`app/schemas/sch_vocabulary.py`):**

```python
from pydantic import BaseModel, Field
from typing import Optional

class VocabularyResponse(BaseModel):
    id: int
    pages_id: int
    word: str
    meaning: str

    model_config = {"from_attributes": True}

class VocabularyCreate(BaseModel):
    pages_id: int
    word: str = Field(max_length=30)
    meaning: str = Field(max_length=35)

class VocabularyUpdate(BaseModel):
    pages_id: Optional[int] = Field(default=None)
    word: Optional[str] = Field(default=None, max_length=30)
    meaning: Optional[str] = Field(default=None, max_length=35)
```

---

## 3. Patrones de Endpoints (Plantillas CRUD)

### Endpoint POST (Creación)

**En `app/api/routes/rt_vocabularies.py`:**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.md_Vocabulary import Vocabulary as tbl_Vocabulary
from app.schemas.sch_vocabulary import VocabularyResponse, VocabularyCreate, VocabularyUpdate

router = APIRouter()

@router.post("/create_vocabulary", response_model=VocabularyResponse)
async def create_vocabulary(vocabulary: VocabularyCreate,
                            conex: AsyncSession = Depends(get_db)):
    try:
        vocabulary_new = tbl_Vocabulary(**vocabulary.model_dump())

        conex.add(vocabulary_new)
        await conex.commit()
        await conex.refresh(vocabulary_new)

        return vocabulary_new

    except IntegrityError:
        await conex.rollback()
        raise HTTPException(status_code=400, detail="Conflicto de datos.")

    except Exception as ex:
        await conex.rollback()
        print(f"Error: {ex}")
        raise HTTPException(status_code=400, detail="Error al registrar")
```

### Endpoint GET (Lectura/Listado)

```python
@router.get("/vocabulary/{pages_id}", response_model=List[VocabularyResponse])
async def get_vocabulary(pages_id: int, conex: AsyncSession = Depends(get_db)):
    try:
        stmt = select(tbl_Vocabulary).where(tbl_Vocabulary.pages_id == pages_id)
        result = await conex.execute(stmt)
        vocabularies = result.scalars().all()

    except Exception as ex:
        print(f"Error de base de datos: {ex}")
        raise HTTPException(status_code=500, detail="Problemas en la petición")

    if not vocabularies:
        raise HTTPException(status_code=404, detail="Verbos no encontrados")

    return vocabularies
```

### Endpoint PATCH (Actualización)

```python
@router.patch("/update_vocabulary/{id}")
async def update_vocabulary(id: int, vocabulary: VocabularyUpdate,
                            conex: AsyncSession = Depends(get_db)):
    try:
        stmt = select(tbl_Vocabulary).where(tbl_Vocabulary.id == id)
        result = await conex.execute(stmt)
        upt_vocabulary = result.scalars().first()

    except Exception as ex:
        print(f"Error de lectura: {ex}")
        raise HTTPException(status_code=500, detail="Problemas en la petición")

    if not upt_vocabulary:
        raise HTTPException(status_code=404, detail="Vocabulario no encontrado")

    try:
        upt_data = vocabulary.model_dump(exclude_unset=True)

        for key, value in upt_data.items():
            setattr(upt_vocabulary, key, value)

        await conex.commit()
        await conex.refresh(upt_vocabulary)
        return upt_vocabulary

    except Exception as ex:
        await conex.rollback()
        print(f"Error: {ex}")
        raise HTTPException(status_code=500, detail="Problemas en la petición")
```

### Endpoint DELETE (Eliminación)

```python
@router.delete("/delete_vocabulary/{id}")
async def delete_vocabulary(id: int, conex: AsyncSession = Depends(get_db)):

    try:
        stmt = select(tbl_Vocabulary).where(tbl_Vocabulary.id == id)
        result = await conex.execute(stmt)
        del_vocabulary = result.scalars().first()

    except Exception as ex:
        print(f"Error al buscar: {ex}")
        raise HTTPException(status_code=500, detail="Problemas en la petición")

    if not del_vocabulary:
        raise HTTPException(status_code=404, detail="Vocabulario no encontrado")

    try:
        await conex.delete(del_vocabulary)
        await conex.commit()

        return {"mensaje": "Vocabulario eliminado correctamente"}

    except Exception as ex:
        await conex.rollback()
        print(f"Error: {ex}")
        raise HTTPException(status_code=500, detail="Problemas en la petición")
```

---

## 4. Convenciones de Nombrado y Tipado Estricto

### Prefijos de Archivos

| Tipo | Prefijo | Ejemplo |
|------|---------|---------|
| Rutas | `rt_` | `rt_verbs.py`, `rt_vocabularies.py`, `rt_pages.py` |
| Modelos | `md_` | `md_Verbs.py`, `md_Vocabulary.py`, `md_Pages.py` |
| Schemas | `sch_` | `sch_verb.py`, `sch_vocabulary.py`, `sch_page.py` |

### Import de Modelos en Rutas

Siempre usa alias con prefijo `tbl_`:

```python
from app.models.md_Vocabulary import Vocabulary as tbl_Vocabulary
from app.models.md_Verbs import Verb as tbl_Verb
from app.schemas.sch_vocabulary import VocabularyResponse, VocabularyCreate, VocabularyUpdate
```

### TYPE_CHECKING para Evitar Imports Circulares

En `app/models/md_Verbs.py`:

```python
from typing import TYPE_CHECKING
from .base import Base

if TYPE_CHECKING:
    from .md_Pages import Page

class Verb(Base):
    __tablename__ = "verbs"
    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    base_form: Mapped[str] = mapped_column(String(25), index=True, nullable=False)
    meaning: Mapped[str] = mapped_column(String(25), nullable=False)
    present: Mapped[str] = mapped_column(String(25), nullable=False)
    simple_past: Mapped[str] = mapped_column(String(25), nullable=False)
    present_part: Mapped[str] = mapped_column(String(25), nullable=False)
    past_part: Mapped[str] = mapped_column(String(25), nullable=False)
    page: Mapped["Page"] = relationship(back_populates="verbs")
```

En `app/models/md_Pages.py` (múltiples relaciones):

```python
from typing import List, TYPE_CHECKING
from .base import Base

if TYPE_CHECKING:
    from .md_Countries import Country
    from .md_Idioms import Idiom
    from .md_Sayings import Saying
    from .md_Synonyms import Synonym
    from .md_Verbs import Verb
    from .md_Vocabulary import Vocabulary

class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_number: Mapped[int] = mapped_column(nullable=False, index=True)
    module_type: Mapped[str] = mapped_column(nullable=False)
    subtitle: Mapped[str] = mapped_column(nullable=False)

    countries: Mapped[List["Country"]] = relationship(back_populates="page", cascade="all, delete-orphan")
    idioms: Mapped[List["Idiom"]] = relationship(back_populates="page", cascade="all, delete-orphan")
    sayings: Mapped[List["Saying"]] = relationship(back_populates="page", cascade="all, delete-orphan")
    synonyms: Mapped[List["Synonym"]] = relationship(back_populates="page", cascade="all, delete-orphan")
    verbs: Mapped[List["Verb"]] = relationship(back_populates="page", cascade="all, delete-orphan")
    vocabularies: Mapped[List["Vocabulary"]] = relationship(back_populates="page", cascade="all, delete-orphan")
```

### Variables

- Variable de conexión: **siempre** `conex` (nunca `db`, `session`)
- Instancias nuevas: `{entity}_new` (vocabulary_new, verb_new)
- Instancias a actualizar: `upt_{entity}` (upt_vocabulary, upt_verb)
- Instancias a eliminar: `del_{entity}` (del_vocabulary, del_verb)

---

## 5. Manejo de Errores y Validaciones

### Validación Automática con Pydantic

- NO valides campos manualmente - confía en Pydantic
- Los esquemas `Create` definen campos requeridos
- Los esquemas `Update` usan `Optional[]` con `default=None`
- FastAPI retorna automáticamente 422 si la validación falla

### Estructura de Try-Except

```python
try:
    # Lógica principal
    new_obj = tbl_Entity(**data.model_dump())
    conex.add(new_obj)
    await conex.commit()
    await conex.refresh(new_obj)
    return new_obj

except IntegrityError:
    await conex.rollback()
    raise HTTPException(status_code=400, detail="Conflicto de datos.")

except Exception as ex:
    await conex.rollback()
    print(f"Error: {ex}")
    raise HTTPException(status_code=400, detail="Error al registrar")
```

### Códigos de Estado HTTP

| Código | Uso |
|--------|-----|
| 200 | Éxito |
| 400 | Error de validación de negocio |
| 404 | Recurso no encontrado |
| 422 | Validación de Pydantic fallida |
| 500 | Error inesperado de servidor |

---

## 6. Estrategia de Testing

### Configuración de Test (`test/conftest.py`)

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import get_db, Base
from app.core.config import settings

SQLALCHEMY_DATABASE_URL = settings.database_ram_url

engine_test = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine_test,
    class_=AsyncSession
)

@pytest.fixture(autouse=True)
async def setup_database():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session

@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client
```

### Tests Representativos (`test/test_vocabularies.py`)

```python
# Test POST exitoso
def test_create_vocabulary_succes(client):
    payload = {
        "pages_id": 1,
        "word": "Deployment",
        "meaning": "Despliegue"
    }

    response = client.post("/api/rt_vocabularies/create_vocabulary", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["word"] == "Deployment"
    assert "id" in data


# Test POST fallido (validación Pydantic)
def test_create_vocabulary_fail(client):
    payload_incompleto = {"word": "Incompleto"}

    response = client.post("/api/rt_vocabularies/create_vocabulary", json=payload_incompleto)

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


# Test GET exitoso
def test_get_vocabulary_succes(client):
    id_pagina_prueba = 5
    payload = {
        "pages_id": id_pagina_prueba,
        "word": "Testing",
        "meaning": "Pruebas"
    }
    client.post("/api/rt_vocabularies/create_vocabulary", json=payload)

    response = client.get(f"/api/rt_vocabularies/vocabulary/{id_pagina_prueba}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["word"] == "Testing"


# Test GET fallido
def test_get_vocabulary_fail(client):
    response = client.get("/api/rt_vocabularies/vocabulary/99")

    assert response.status_code == 404
    assert response.json()["detail"] == "Verbos no encontrados"


# Test PATCH exitoso
def test_update_vocabulary_success(client):
    payload_crear = {"pages_id": 1, "word": "Bug", "meaning": "Bicho"}
    response_post = client.post("/api/rt_vocabularies/create_vocabulary", json=payload_crear)
    id_creado = response_post.json()["id"]

    payload_patch = {"meaning": "Error de software"}
    response_patch = client.patch(f"/api/rt_vocabularies/update_vocabulary/{id_creado}", json=payload_patch)

    assert response_patch.status_code == 200
    data = response_patch.json()
    assert data["meaning"] == "Error de software"
    assert data["word"] == "Bug"


# Test PATCH fallido
def test_update_vocabulary_fail(client):
    payload_patch = {"word": "Fantasma"}

    response = client.patch("/api/rt_vocabularies/update_vocabulary/999", json=payload_patch)

    assert response.status_code == 404
    assert response.json()["detail"] == "Vocabulario no encontrado"


# Test DELETE exitoso
def test_delete_vocabulary_success(client):
    payload_crear = {"pages_id": 1, "word": "DeleteMe", "meaning": "Bórrame"}
    response_post = client.post("/api/rt_vocabularies/create_vocabulary", json=payload_crear)
    id_creado = response_post.json()["id"]

    response_delete = client.delete(f"/api/rt_vocabularies/delete_vocabulary/{id_creado}")

    assert response_delete.status_code == 200
    assert response_delete.json()["mensaje"] == "Vocabulario eliminado correctamente"

    response_verificar = client.get("/api/rt_vocabularies/vocabulary/1")
    assert response_verificar.status_code == 404


# Test DELETE fallido
def test_delete_vocabulary_fail(client):
    response = client.delete("/api/rt_vocabularies/delete_vocabulary/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Vocabulario no encontrado"
```

### Reglas de Testing

- Usa `database_ram_url` (aiosqlite) para tests, NO PostgreSQL
- Fixture `autouse=True` crea/dropea tablas automáticamente en cada test
- Override de `get_db` con `TestingSessionLocal`
- Tests de éxito: crear recurso primero, luego verificar
- Tests de fracaso: verificar mensaje en `response.json()["detail"]`

---

## 7. Registro de Routers en main.py

```python
from app.api.routes.rt_pages import router as router_Page
from app.api.routes.rt_vocabularies import router as router_Vocabulary
from app.api.routes.rt_verbs import router as router_Verb
from app.api.routes.rt_synonyms import router as router_Synonym
from app.api.routes.rt_sayings import router as router_Saying
from app.api.routes.rt_idioms import router as router_Idiom
from app.api.routes.rt_countries import router as router_Country

app.include_router(router_Page, prefix="/api/rt_pages", tags=["page"])
app.include_router(router_Vocabulary, prefix="/api/rt_vocabularies", tags=["vocabularies"])
app.include_router(router_Verb, prefix="/api/rt_verbs", tags=["verbs"])
app.include_router(router_Synonym, prefix="/api/rt_synonyms", tags=["synonyms"])
app.include_router(router_Saying, prefix="/api/rt_sayings", tags=["sayings"])
app.include_router(router_Idiom, prefix="/api/rt_idioms", tags=["idioms"])
app.include_router(router_Country, prefix="/api/rt_countries", tags=["countries"])
```

---

## 8. Instrucciones Imperativas

1. **Siempre define modelos asíncronos de esta manera:**
   ```python
   from sqlalchemy.orm import Mapped, mapped_column, relationship
   from typing import TYPE_CHECKING
   from .base import Base

   if TYPE_CHECKING:
       from .md_Pages import Page

   class Entity(Base):
       __tablename__ = "entities"
       id: Mapped[int] = mapped_column(primary_key=True)
       campo: Mapped[str] = mapped_column(String(30))
       related: Mapped["Related"] = relationship(back_populates="entities")
   ```

2. **Siempre crea la conexión asíncrona con este patrón:**
   ```python
   engine = create_async_engine(url, echo=False, pool_pre_ping=True)
   SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession)
   async def get_db():
       async with SessionLocal() as session:
           yield session
   ```

3. **Siempre nombra la variable de conexión como `conex`:**
   ```python
   async def endpoint(entity: EntityCreate, conex: AsyncSession = Depends(get_db)):
   ```

4. **Siempre importa modelos con alias `tbl_`:**
   ```python
   from app.models.md_Vocabulary import Vocabulary as tbl_Vocabulary
   ```

5. **Siempre usa prefijos en archivos:**
   - Rutas: `rt_*.py`
   - Modelos: `md_*.py`
   - Schemas: `sch_*.py`

6. **Siempre usa Pydantic schemas con esta estructura:**
   ```python
   class EntityResponse(BaseModel):
       id: int
       campo: str
       model_config = {"from_attributes": True}

   class EntityCreate(BaseModel):
       campo: str = Field(max_length=30)

   class EntityUpdate(BaseModel):
       campo: Optional[str] = Field(default=None, max_length=30)
   ```

7. **Siempre haz rollback en excepciones:**
   ```python
   except Exception as ex:
       await conex.rollback()
       print(f"Error: {ex}")
       raise HTTPException(status_code=500, detail="Problema")
   ```

8. **Siempre usa TYPE_CHECKING para evitar imports circulares:**
   ```python
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       from .md_Pages import Page
   ```

9. **Siempre usa cascade en relaciones:**
   ```python
   page: Mapped["Page"] = relationship(back_populates="vocabularies", cascade="all, delete-orphan")
   ```

10. **Siempre usa Field de Pydantic para validaciones de longitud:**
    ```python
    word: str = Field(max_length=30)
    meaning: str = Field(max_length=35)
    ```

11. **Siempre inyecta la dependencia de base de datos:**
    ```python
    @router.post("/create_entity")
    async def create(entity: EntityCreate, conex: AsyncSession = Depends(get_db)):
    ```

12. **Siempre convierte con model_dump en create:**
    ```python
    new_obj = tbl_Entity(**entity.model_dump())
    ```

13. **Siempre usa model_dump(exclude_unset=True) en update:**
    ```python
    upt_data = entity.model_dump(exclude_unset=True)
    for key, value in upt_data.items():
        setattr(upt_obj, key, value)
    ```

14. **Siempre retorna el objeto creado/actualizado:**

    ```python
    return vocabulary_new  # En POST
    return vocabularies   # En GET
    return upt_vocabulary # En PATCH
    return {"mensaje": "Eliminado"} # En DELETE
    ```

15. **Siempre configura CORS con orígenes explícitos:**

    ```python
    origins = [settings.url_localhost_frontend, settings.url_produccion]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True)
    ```

16. **Siempre usa settings.database_ram_url para tests:**

    ```python
    SQLALCHEMY_DATABASE_URL = settings.database_ram_url  # aiosqlite
    ```

17. **Siempre crea fixtures de test con autouse:**

    ```python
    @pytest.fixture(autouse=True)
    async def setup_database():
        async with engine_test.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield
        async with engine_test.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    ```

18. **Siempre haz commit después de add/actualizar/eliminar:**

    ```python
    conex.add(new_obj)
    await conex.commit()
    await conex.refresh(new_obj)
    ```

19. **Siempre haz select con where y extrae con scalars:**

    ```python
    stmt = select(tbl_Vocabulary).where(tbl_Vocabulary.pages_id == pages_id)
    result = await conex.execute(stmt)
    vocabularies = result.scalars().all()  # o .first()
    ```

20. **Siempre registra routers con tags:**

    ```python
    app.include_router(router_Vocabulary, prefix="/api/rt_vocabularies", tags=["vocabularies"])
    ```

---

## 9. Convenciones Adicionales

- **Comentarios en español** dentro del código
- **Logging con print** en desarrollo (no logger externo)
- **Migraciones con Alembic**
- **Variables de entorno en `.env`** con pydantic-settings
- **Base declarativa en `models/base.py`**:
  ```python
  from sqlalchemy.orm import DeclarativeBase
  class Base(DeclarativeBase):
      pass
  ```

Este guide debe seguirse exactamente para que cualquier código generado sea indistinguible del código original de DavidZuniga.