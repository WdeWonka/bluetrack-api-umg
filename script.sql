-- =========================================================
-- PROYECTO: Sistema de Monitoreo y Rutas de Vendedores
-- FECHA: 2025-10-08
-- =========================================================

-- Crear la base de datos si no existe
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = N'blue_track_db')
BEGIN
    CREATE DATABASE blue_track_db;
END
GO

-- Seleccionar la base de datos
USE blue_track_db;
GO

-- =========================================================
-- Limpieza previa: eliminar tablas si existen
-- =========================================================
IF OBJECT_ID('entregas', 'U') IS NOT NULL DROP TABLE entregas;
IF OBJECT_ID('inventario_ruta', 'U') IS NOT NULL DROP TABLE inventario_ruta;
IF OBJECT_ID('ruta_detalle', 'U') IS NOT NULL DROP TABLE ruta_detalle;
IF OBJECT_ID('rutas', 'U') IS NOT NULL DROP TABLE rutas;
IF OBJECT_ID('productos', 'U') IS NOT NULL DROP TABLE productos;
IF OBJECT_ID('clientes', 'U') IS NOT NULL DROP TABLE clientes;
IF OBJECT_ID('almacenes', 'U') IS NOT NULL DROP TABLE almacenes;
IF OBJECT_ID('usuarios', 'U') IS NOT NULL DROP TABLE usuarios;
GO

-- =========================================================
-- 1. Tabla de Usuarios
-- Admin y Vendedores
-- =========================================================
CREATE TABLE usuarios (
    id INT IDENTITY(1,1) PRIMARY KEY,
    dpi NVARCHAR(20) UNIQUE NOT NULL,
    nombre NVARCHAR(100) NOT NULL,
    email NVARCHAR(100) UNIQUE NOT NULL,
    password NVARCHAR(255) NOT NULL,
    rol NVARCHAR(20) CHECK (rol IN ('admin','operador' ,'vendedor')) NOT NULL,
    activo BIT DEFAULT 1,
    creado_en DATETIME DEFAULT GETDATE()
);

-- =========================================================
-- 2. Tabla de Almacenes
-- Puntos de inicio de las rutas
-- =========================================================
CREATE TABLE almacenes (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nombre NVARCHAR(100) NOT NULL,
    direccion NVARCHAR(255) UNIQUE NOT NULL,
    telefono NVARCHAR(20) UNIQUE NOT NULL,
    latitud DECIMAL(10,6),
    longitud DECIMAL(10,6),
    creado_en DATETIME DEFAULT GETDATE()
);

-- =========================================================
-- 3. Tabla de Clientes
-- Datos de los clientes a los que se entregan productos
-- =========================================================
CREATE TABLE clientes (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nombre NVARCHAR(120) NOT NULL,
    direccion NVARCHAR(255) UNIQUE NOT NULL,
    telefono NVARCHAR(20) UNIQUE NOT NULL,
    latitud DECIMAL(10,6),
    longitud DECIMAL(10,6),
    creado_en DATETIME DEFAULT GETDATE()
);

-- =========================================================
-- 4. Tabla de Productos
-- =========================================================
CREATE TABLE productos (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nombre NVARCHAR(120) UNIQUE NOT NULL,
    precio DECIMAL(10,2) NOT NULL,
    stock_total INT DEFAULT 0,
    activo BIT DEFAULT 1,
    creado_en DATETIME DEFAULT GETDATE()
);

-- =========================================================
-- 5. Tabla de Rutas
-- Planificación de rutas asignadas a vendedores
-- =========================================================
CREATE TABLE rutas (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nombre NVARCHAR(120) NOT NULL,
    vendedor_id INT NOT NULL,   -- referencia al vendedor
    almacen_id INT NOT NULL,    -- referencia al almacén de inicio
    fecha DATE NOT NULL,        -- fecha planificada de la ruta
    estado NVARCHAR(20) CHECK (estado IN ('pendiente', 'en_proceso', 'completada')) DEFAULT 'pendiente',
    inicio_timestamp DATETIME NULL,  -- se llena cuando vendedor comienza la ruta
    fin_timestamp DATETIME NULL,     -- se llena cuando vendedor termina la ruta
    creado_en DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (vendedor_id) REFERENCES usuarios(id),
    FOREIGN KEY (almacen_id) REFERENCES almacenes(id)
);

-- =========================================================
-- 6. Tabla de Ruta Detalle
-- Clientes asignados a una ruta, con estado de entrega
-- =========================================================
CREATE TABLE ruta_detalle (
    id INT IDENTITY(1,1) PRIMARY KEY,
    ruta_id INT NOT NULL,
    cliente_id INT NOT NULL,
    orden INT NOT NULL,  -- orden en que se visitará al cliente
    estado_entrega NVARCHAR(20) CHECK (estado_entrega IN ('entregado', 'no_entregado')) DEFAULT 'no_entregado',
    motivo NVARCHAR(255) NULL,        -- si no se entrega, se registra el motivo
    timestamp_entrega DATETIME NULL,   -- se llena cuando se registra entrega
    creado_en DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ruta_id) REFERENCES rutas(id) ON DELETE CASCADE,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

-- =========================================================
-- 7. Tabla de Órdenes
-- Órdenes/pedidos de clientes pendientes de asignar a una ruta
-- =========================================================

CREATE TABLE ordenes (
    id INT IDENTITY(1,1) PRIMARY KEY,
    cliente_id INT NOT NULL,
    producto_id INT NOT NULL,
    cantidad INT NOT NULL,
    prioridad NVARCHAR(20) DEFAULT 'normal' CHECK (prioridad IN ('alta','normal','baja')),
    fecha_solicitud DATETIME DEFAULT GETDATE(),
    asignada BIT DEFAULT 0,  -- True si ya está en una ruta
    ruta_id INT NULL,
    creado_en DATETIME DEFAULT GETDATE(),

    CONSTRAINT FK_ordenes_clientes FOREIGN KEY (cliente_id) REFERENCES clientes(id),
    CONSTRAINT FK_ordenes_productos FOREIGN KEY (producto_id) REFERENCES productos(id),
    CONSTRAINT FK_ordenes_rutas FOREIGN KEY (ruta_id) REFERENCES rutas(id)
);

-- =========================================================
-- 8. Tabla de Entregas
-- Productos entregados por cliente en cada ruta
-- =========================================================
CREATE TABLE entregas (
    id INT IDENTITY(1,1) PRIMARY KEY,
    ruta_detalle_id INT NOT NULL,
    orden_id INT NULL,
    producto_id INT NOT NULL,
    cantidad INT CHECK (cantidad >= 0),
    creado_en DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ruta_detalle_id) REFERENCES ruta_detalle(id) ON DELETE CASCADE,
    FOREIGN KEY (orden_id) REFERENCES ordenes(id) ON DELETE SET NULL,
    FOREIGN KEY (producto_id) REFERENCES productos(id)
);

-- =========================================================
-- 9. Tabla de Inventario Ruta
-- Productos cargados en cada ruta
-- =========================================================
CREATE TABLE inventario_ruta (
    id INT IDENTITY(1,1) PRIMARY KEY,
    ruta_id INT NOT NULL,
    producto_id INT NOT NULL,
    cantidad_inicial INT NOT NULL,
    cantidad_final INT NULL,
    creado_en DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ruta_id) REFERENCES rutas(id) ON DELETE CASCADE,
    FOREIGN KEY (producto_id) REFERENCES productos(id)
);
