# Bluetrack API - UMG

![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)
![Docker](https://img.shields.io/badge/Docker-Compose-blue?logo=docker)
![GitHub](https://img.shields.io/badge/GitHub-Repo-black?logo=github)
![Status](https://img.shields.io/badge/Status-Stable-brightgreen)

Backend API para Bluetrack, desarrollada con Python y FastAPI.  
Gestiona inventarios, distribución de agua, autenticación JWT y conexión a SQL Server.  

---

## Project Status

Bluetrack API se encuentra en **versión estable inicial**.  
Colaboradores deben crear ramas separadas para nuevas funcionalidades y enviar pull requests para revisión antes de mergear a `main`.  
¡Happy coding! 🚀

---

## Requirements

Antes de levantar el proyecto asegúrate de tener instalados:

- **Python 3.13+**
- **pip** (viene con Python)
- **Docker & Docker Compose**
- **Git**
- Opcional: editor como **VS Code** para desarrollo y un IDE para base de datos que maneje SQL SERVER **DataGrip**

---

## Installation

1. Clonar el repositorio:

```
git clone https://github.com/<tu-usuario>/bluetrack-api-umg.git
```
2. Navegar al directorio del proyecto:
```
cd bluetrack-api-umg
```
3. Crear entorno virtual:
```
python -m venv venv
```
# Windows
```
venv\Scripts\activate
```
# Linux / Mac
```
source venv/bin/activate
```
4. Instalar dependencias de Python:
```
pip install -r requirements.txt
```
## Configuration
5. Corre el Docker Compose usando el comando de `./config/dev.docker-compose.yml`:
    ```
   docker compose up -d
   ```
6. Dentro de root `./`, crear el archivo  `.env` para configurar las variables de entorno:
   cp .env.example .env
  `Guiarse del archivo env.example`

### Usage
### Development
Para correr el proyecto:
```
uvicorn main:app --reload
```
   







