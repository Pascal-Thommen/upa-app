# Guia para Agentes de IA y Desarrolladores (AGENTS.md)

Este documento contiene las directrices centrales de trabajo para todos los agentes autonomos de programacion (Cursor, Claude Code, GitHub Copilot, Antigravity) y desarrolladores del proyecto UPA App.

## 1. Descripcion General y Arquitectura
El proyecto es una plataforma universitaria para la Universidad Paraguayo Alemana (UPA):
* `android/`: Aplicacion nativa para Android (Android Studio, Kotlin).
* `backend/`: Servicio REST API desarrollado con Python 3.11+ y FastAPI.
* `web-admin/`: Portal web ligero para edicion y marketing (version escritorio).
* `docs/`: Definicion de contratos de API, modelos de datos y especificaciones.

## 2. Politica de Seguridad: Cero Secretos en el Repositorio
Todos los agentes deben cumplir estrictamente las siguientes reglas:
* Nunca incluir claves de API reales, secretos de clientes OAuth, archivos de service accounts ni contrasenas en commits.
* La configuracion se realiza exclusivamente mediante variables de entorno (.env).
* Antes de cada commit, verificar que ningun dato privado o clave este hardcodeado en codigo, logs o pruebas.
* Nuevas variables de entorno deben documentarse con valores de ejemplo en `.env.example`.

## 3. Principios de Arquitectura y Convenciones
* Idioma del Repositorio: Toda la documentacion, nombres de commits y comentarios de codigo se redactan en espanol.
* API First: El backend expone una especificacion OpenAPI/Swagger interactiva en `/docs`. Los cambios de interfaz deben ser compatibles con versiones anteriores.
* Single Source of Truth: Las publicaciones y eventos de calendario comparten el mismo modelo de datos relacional (hibrido post/evento).
* Autenticacion: Google OAuth 2.0 con validacion estricta de dominio de correo (`@upa.edu.py`).
* Modularidad: Cada componente (Android, Backend, Web-Admin) trabaja de forma independiente y se comunica mediante la API REST.

## 4. Comandos Utiles
* Iniciar Backend: `cd backend && uvicorn src.main:app --reload --port 8000`
* Ejecutar Pruebas: `pytest` dentro del directorio backend.
