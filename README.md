# UPA App

Plataforma universitaria central para estudiantes y docentes de la Universidad Paraguayo Alemana (UPA).

## Estructura del Proyecto

```text
upa-app/
├── android/          # Aplicacion nativa Android (Android Studio / Kotlin)
├── backend/          # Servicio REST API (Python, FastAPI, Pydantic, SQLAlchemy)
├── web-admin/        # Portal web para administracion y marketing (Escritorio)
├── docs/             # Especificaciones, modelos de datos y briefing docente
├── .github/          # Flujos de CI/CD y verificaciones de seguridad
├── AGENTS.md         # Instrucciones de trabajo para agentes autonomos de IA
└── README.md
```

## Modulos y Funcionalidades Principales

1. **Inicio (Feed del Campus):**
   * Avisos de emergencia como banner superior (ej. suspension de clases por tormenta).
   * Eventos del campus y conferencias (Charlas) con registro e inscripcion en 1 clic.
   * Agregacion automatica de redes sociales oficiales via SociableKIT / Instagram API.

2. **Agenda (Calendario y Entregas):**
   * Vista combinada: Lista cronologica arriba y calendario mensual con puntos de actividad abajo.
   * Sincronizacion automatica de plazos y tareas academicas via Google Classroom.

3. **Perfil y Configuracion:**
   * Inicio de sesion obligatorio via Google OAuth restringido a cuentas `@upa.edu.py`.
   * Preferencias locales del usuario (modo oscuro/claro, notificaciones, filtro de carrera).

4. **Administracion Web (Portal de Escritorio):**
   * Sistema de gestion de contenidos para el equipo de marketing.
   * Fuente unica de verdad (Single Source of Truth): una publicacion puede ser post, evento de agenda o ambos.
   * Segmentacion de destinatarios basada en Google Groups mediante Google Workspace Admin API.

## Politica de Seguridad y Codigo Abierto

Este repositorio es publico. Todos los desarrolladores y agentes de IA deben cumplir estrictamente:
* Prohibido incluir claves API reales, secretos o datos personales en los commits.
* Todas las configuraciones se gestionan mediante archivos `.env` protegidos por `.gitignore`.
* Las variables requeridas se documentan con valores de ejemplo en `.env.example`.

## Inicio Rapido del Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn src.main:app --reload --port 8000
```

Documentacion interactiva de la API disponible en: `http://localhost:8000/docs`
