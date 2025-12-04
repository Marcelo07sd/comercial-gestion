# models.py - Basado 100% en el esquema SQL Server (sin créditos)
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from sqlalchemy import event
import random

db = SQLAlchemy()

# Configurar la zona horaria de Perú (UTC-5)
def hora_peru():
    """Obtiene la hora actual en Perú (UTC-5)"""
    return datetime.utcnow() - timedelta(hours=5)


class Cliente(db.Model):
    """Modelo Cliente - Exactamente como en SQL Server"""
    __tablename__ = 'Cliente'
    
    id_cliente = db.Column(db.Integer, primary_key=True, autoincrement=True)
    dni = db.Column(db.String(8), unique=True, nullable=False, index=True)
    nombres = db.Column(db.String(50), nullable=False, index=True)
    apellidos = db.Column(db.String(50), nullable=False)
    direccion = db.Column(db.String(100))
    telefono = db.Column(db.String(9))
    
    # Relaciones
    ventas = db.relationship('Venta', backref='cliente', lazy=True)
    
    def __repr__(self):
        return f'<Cliente {self.nombres} {self.apellidos}>'


class Usuario(UserMixin, db.Model):
    """Modelo Usuario - Del esquema SQL Server con Flask-Login"""
    __tablename__ = 'Usuario'
    
    id_usuario = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(30), nullable=False)  # admin, vendedor, consulta
    nombre_completo = db.Column(db.String(120))
    fecha_creacion = db.Column(db.DateTime, default=hora_peru)
    activo = db.Column(db.Boolean, default=True)
    
    # Relaciones
    ventas = db.relationship('Venta', backref='vendedor', lazy=True)
    
    def get_id(self):
        """Requerido por Flask-Login"""
        return str(self.id_usuario)
    
    def set_password(self, password):
        """Hash de contraseña"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verificar contraseña"""
        return check_password_hash(self.password_hash, password)
    
    def tiene_permiso(self, accion):
        """Sistema de permisos según rol"""
        permisos = {
            'admin': ['crear', 'leer', 'actualizar', 'eliminar', 'ventas', 'reportes'],
            'vendedor': ['leer', 'ventas', 'actualizar_cliente'],
            'consulta': ['leer', 'reportes']
        }
        return accion in permisos.get(self.rol, [])
    
    def __repr__(self):
        return f'<Usuario {self.username} - {self.rol}>'


class Producto(db.Model):
    """Modelo Producto - Del esquema SQL Server"""
    __tablename__ = 'Producto'
    
    id_producto = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_producto = db.Column(db.String(100), nullable=False, index=True)
    descripcion = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    
    # Relaciones
    detalles_venta = db.relationship('DetalleVenta', backref='producto', lazy=True)
    
    def __repr__(self):
        return f'<Producto {self.nombre_producto}>'


class Venta(db.Model):
    """Modelo Venta - Del esquema SQL Server"""
    __tablename__ = 'Venta'
    
    id_venta = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fecha_venta = db.Column(db.Date, nullable=False, default=lambda: hora_peru().date())
    id_cliente = db.Column(db.Integer, db.ForeignKey('Cliente.id_cliente'), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey('Usuario.id_usuario'), nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    
    # Relaciones
    detalles = db.relationship('DetalleVenta', backref='venta', lazy=True, cascade='all, delete-orphan')
    
    def calcular_total(self):
        """Calcula el total de la venta sumando los detalles"""
        self.total = sum(detalle.subtotal for detalle in self.detalles)
        return self.total
    
    def __repr__(self):
        return f'<Venta {self.id_venta} - Total: {self.total}>'


class DetalleVenta(db.Model):
    """Modelo DetalleVenta - Del esquema SQL Server"""
    __tablename__ = 'DetalleVenta'
    
    id_detalle = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_venta = db.Column(db.Integer, db.ForeignKey('Venta.id_venta'), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('Producto.id_producto'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    
    @property
    def subtotal(self):
        """Calcula el subtotal (cantidad * precio_unitario) - Columna calculada en SQL"""
        return float(self.cantidad) * float(self.precio_unitario)
    
    def __repr__(self):
        return f'<DetalleVenta {self.id_detalle}>'


class Auditoria(db.Model):
    """Modelo Auditoria - Del esquema SQL Server"""
    __tablename__ = 'Auditoria'
    
    id_auditoria = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tabla = db.Column(db.String(50))
    accion = db.Column(db.String(10))
    id_registro = db.Column(db.Integer)
    fecha = db.Column(db.DateTime, default=hora_peru)
    usuario_sql = db.Column(db.String(100))
    datos = db.Column(db.Text)
    
    def __repr__(self):
        return f'<Auditoria {self.tabla} - {self.accion}>'


# ===== EVENTOS (TRIGGERS) =====

@event.listens_for(Producto, 'after_insert')
def auditoria_producto_insert(mapper, connection, target):
    """Trigger: Auditoría al insertar producto"""
    auditoria = Auditoria(
        tabla='Producto',
        accion='INSERT',
        id_registro=target.id_producto,
        usuario_sql='system',
        datos=f'Producto: {target.nombre_producto}, Precio: {target.precio}, Stock: {target.stock}'
    )
    db.session.add(auditoria)


@event.listens_for(Producto, 'after_update')
def auditoria_producto_update(mapper, connection, target):
    """Trigger: Auditoría al actualizar producto"""
    auditoria = Auditoria(
        tabla='Producto',
        accion='UPDATE',
        id_registro=target.id_producto,
        usuario_sql='system',
        datos=f'Producto actualizado: {target.nombre_producto}'
    )
    db.session.add(auditoria)


@event.listens_for(Producto, 'after_delete')
def auditoria_producto_delete(mapper, connection, target):
    """Trigger: Auditoría al eliminar producto"""
    auditoria = Auditoria(
        tabla='Producto',
        accion='DELETE',
        id_registro=target.id_producto,
        usuario_sql='system',
        datos=f'Producto eliminado: {target.nombre_producto}'
    )
    db.session.add(auditoria)


# ===== FUNCIÓN DE NEGOCIO (SP_REGISTRAR_VENTA) =====

def registrar_venta(id_cliente, id_usuario, fecha=None, detalles_productos=None):
    """
    Replica el SP sp_RegistrarVenta del SQL Server
    
    Args:
        id_cliente: ID del cliente
        id_usuario: ID del usuario/vendedor
        fecha: Fecha de la venta (opcional, si es None usa fecha actual Perú)
        detalles_productos: Lista de dicts [{id_producto, cant, precio}, ...]
    
    Returns:
        dict: {'status': 'success'|'error', 'mensaje': str, 'venta_id': int, 'total_venta': float}
    """
    if detalles_productos is None:
        detalles_productos = []
    
    try:
        # Usar fecha actual de Perú si no se especifica
        if fecha is None:
            fecha = hora_peru().date()
        
        # 1. VERIFICAR STOCK DISPONIBLE
        for detalle in detalles_productos:
            producto = Producto.query.get(detalle['id_producto'])
            if not producto:
                return {
                    'status': 'error',
                    'mensaje': f"Producto ID {detalle['id_producto']} no encontrado",
                    'venta_id': 0,
                    'total_venta': 0
                }
            
            if producto.stock < detalle['cant']:
                return {
                    'status': 'error',
                    'mensaje': f"Stock insuficiente para '{producto.nombre_producto}' (ID: {producto.id_producto}). "
                              f"Solicitado: {detalle['cant']}, Disponible: {producto.stock}",
                    'venta_id': 0,
                    'total_venta': 0
                }
        
        # 2. INSERTAR VENTA
        venta = Venta(
            fecha_venta=fecha,
            id_cliente=id_cliente,
            id_usuario=id_usuario,
            total=0
        )
        db.session.add(venta)
        db.session.flush()  # Obtener id_venta
        
        id_venta = venta.id_venta
        total = 0
        
        # 3. INSERTAR DETALLES DE VENTA
        for detalle in detalles_productos:
            detalle_venta = DetalleVenta(
                id_venta=id_venta,
                id_producto=detalle['id_producto'],
                cantidad=detalle['cant'],
                precio_unitario=detalle['precio']
            )
            db.session.add(detalle_venta)
            total += detalle_venta.subtotal
        
        # 4. CALCULAR Y ACTUALIZAR TOTAL
        venta.total = total
        
        # 5. ACTUALIZAR STOCK DE PRODUCTOS
        for detalle in detalles_productos:
            producto = Producto.query.get(detalle['id_producto'])
            producto.stock -= detalle['cant']
        
        # 6. REGISTRAR EN AUDITORÍA
        auditoria = Auditoria(
            tabla='Venta',
            accion='INSERT',
            id_registro=id_venta,
            usuario_sql='system',
            datos=f'Venta registrada: Cliente ID {id_cliente}, Total S/. {total:.2f}'
        )
        db.session.add(auditoria)
        
        # 7. COMMIT
        db.session.commit()
        
        return {
            'status': 'success',
            'mensaje': 'Venta registrada exitosamente',
            'venta_id': id_venta,
            'total_venta': float(total)
        }
        
    except Exception as e:
        db.session.rollback()
        return {
            'status': 'error',
            'mensaje': f'Error al registrar venta: {str(e)}',
            'venta_id': 0,
            'total_venta': 0
        }


# ===== DATOS INICIALES =====

def crear_ventas_historicas():
    """Crea ventas históricas para tener datos realistas en el sistema"""
    try:
        # Obtener usuarios
        admin = Usuario.query.filter_by(username='admin').first()
        vendedor1 = Usuario.query.filter_by(username='vendedor1').first()
        vendedor2 = Usuario.query.filter_by(username='vendedor2').first()
        
        # Obtener algunos clientes
        clientes = Cliente.query.limit(15).all()
        
        # Obtener productos con sus precios actuales
        productos = Producto.query.all()
        
        if not productos or not clientes or not admin:
            print("⚠ No hay suficientes datos para crear ventas históricas")
            return
        
        hoy = hora_peru().date()
        
        # Ventas predefinidas con fechas variadas
        ventas_config = [
            # Ventas recientes (última semana)
            {
                'fecha': hoy - timedelta(days=1),
                'cliente_idx': 0, 'vendedor': vendedor1,
                'detalles': [(1, 1), (3, 2), (7, 1)]  # (id_producto, cantidad)
            },
            {
                'fecha': hoy - timedelta(days=2),
                'cliente_idx': 1, 'vendedor': vendedor2,
                'detalles': [(2, 1), (5, 1)]
            },
            {
                'fecha': hoy - timedelta(days=3),
                'cliente_idx': 2, 'vendedor': admin,
                'detalles': [(10, 1), (15, 2), (20, 1), (25, 1)]
            },
            {
                'fecha': hoy - timedelta(days=4),
                'cliente_idx': 3, 'vendedor': vendedor1,
                'detalles': [(30, 1), (35, 1)]
            },
            {
                'fecha': hoy - timedelta(days=5),
                'cliente_idx': 4, 'vendedor': vendedor2,
                'detalles': [(4, 1), (8, 2), (12, 1)]
            },
            
            # Ventas de hace 2 semanas
            {
                'fecha': hoy - timedelta(days=10),
                'cliente_idx': 5, 'vendedor': admin,
                'detalles': [(6, 1), (9, 1), (11, 1)]
            },
            {
                'fecha': hoy - timedelta(days=12),
                'cliente_idx': 6, 'vendedor': vendedor1,
                'detalles': [(14, 1), (18, 2)]
            },
            {
                'fecha': hoy - timedelta(days=14),
                'cliente_idx': 7, 'vendedor': vendedor2,
                'detalles': [(22, 1), (27, 1), (32, 1)]
            },
            
            # Ventas del mes pasado
            {
                'fecha': hoy - timedelta(days=20),
                'cliente_idx': 8, 'vendedor': admin,
                'detalles': [(3, 1), (16, 1), (28, 2)]
            },
            {
                'fecha': hoy - timedelta(days=25),
                'cliente_idx': 9, 'vendedor': vendedor1,
                'detalles': [(5, 1), (13, 1), (21, 1), (29, 1)]
            },
            {
                'fecha': hoy - timedelta(days=28),
                'cliente_idx': 10, 'vendedor': vendedor2,
                'detalles': [(19, 1), (24, 1), (33, 2)]
            },
            {
                'fecha': hoy - timedelta(days=30),
                'cliente_idx': 11, 'vendedor': admin,
                'detalles': [(17, 1), (26, 1), (34, 1)]
            },
            
            # Ventas grandes
            {
                'fecha': hoy - timedelta(days=7),
                'cliente_idx': 12, 'vendedor': admin,
                'detalles': [(1, 1), (2, 1), (10, 1), (15, 1), (20, 1), (25, 1)]
            },
            {
                'fecha': hoy - timedelta(days=15),
                'cliente_idx': 13, 'vendedor': vendedor1,
                'detalles': [(8, 2), (12, 2), (18, 1), (23, 1)]
            },
            {
                'fecha': hoy - timedelta(days=22),
                'cliente_idx': 14, 'vendedor': vendedor2,
                'detalles': [(4, 1), (9, 1), (14, 1), (19, 1), (30, 1)]
            }
        ]
        
        ventas_creadas = 0
        total_general = 0
        
        for venta_config in ventas_config:
            try:
                if venta_config['cliente_idx'] < len(clientes):
                    cliente = clientes[venta_config['cliente_idx']]
                    detalles_productos = []
                    
                    for prod_id, cantidad in venta_config['detalles']:
                        if prod_id <= len(productos):
                            producto = productos[prod_id - 1]
                            detalles_productos.append({
                                'id_producto': producto.id_producto,
                                'cant': cantidad,
                                'precio': float(producto.precio)
                            })
                    
                    if detalles_productos:
                        # Crear venta usando la función registrar_venta
                        resultado = registrar_venta(
                            id_cliente=cliente.id_cliente,
                            id_usuario=venta_config['vendedor'].id_usuario,
                            fecha=venta_config['fecha'],
                            detalles_productos=detalles_productos
                        )
                        
                        if resultado['status'] == 'success':
                            ventas_creadas += 1
                            total_general += resultado['total_venta']
                        
            except Exception as e:
                print(f"⚠ Error creando venta histórica: {e}")
                continue
        
        # Crear algunas auditorías manuales para simular actividad
        if productos:
            for i in range(1, 6):
                idx = min(i * 3, len(productos) - 1)
                producto = productos[idx]
                
                auditoria = Auditoria(
                    tabla='Producto',
                    accion='UPDATE',
                    id_registro=producto.id_producto,
                    usuario_sql='admin',
                    datos=f'Ajuste de stock del producto: {producto.nombre_producto}. Stock anterior: {producto.stock + 5}, Stock actual: {producto.stock}',
                    fecha=hora_peru() - timedelta(days=random.randint(1, 20))
                )
                db.session.add(auditoria)
        
        db.session.commit()
        
        print(f"\n✓ {ventas_creadas} ventas históricas creadas")
        print(f"✓ Total generado en ventas históricas: S/. {total_general:.2f}")
        print("✓ Auditorías adicionales registradas")
        
    except Exception as e:
        print(f"⚠ Error en crear_ventas_historicas: {e}")
        db.session.rollback()


def inicializar_datos():
    """Inicializa la base de datos con datos del SQL Server"""
    db.create_all()
    
    if Usuario.query.first():
        print("✓ La base de datos ya contiene datos")
        # Solo crear ventas históricas si no hay ventas
        if Venta.query.count() == 0:
            crear_ventas_historicas()
        return
    
    print("Inicializando base de datos SistemaVentasDB...")
    print(f"Hora Perú actual: {hora_peru()}")
    
    # 1. USUARIOS (del script SQL Server)
    usuarios_data = [
        ('admin', 'AdminSecure123', 'admin', 'Raúl Gómez (Administrador)'),
        ('vendedor1', 'VendedorSecure456', 'vendedor', 'Ana López (Vendedora)'),
        ('vendedor2', 'VendedorSecure456', 'vendedor', 'María García (Vendedora)'),
        ('consulta1', 'ConsultaSecure789', 'consulta', 'Antonio Ruiz (Consultor)')
    ]
    
    for username, password, rol, nombre in usuarios_data:
        usuario = Usuario(
            username=username,
            rol=rol,
            nombre_completo=nombre
        )
        usuario.set_password(password)
        db.session.add(usuario)
    
    # 2. CLIENTES ADICIONALES (más clientes del distrito SJL, Lima) CON DNIS ÚNICOS
    clientes_data = [
        ('71234567', 'Juan', 'Pérez', 'Jr. Las Perlas 123, SJL', '987654321'),
        ('82345678', 'María', 'García', 'Jr. Los Zafiros 456, SJL', '912345678'),
        ('93456789', 'Carlos', 'Rodríguez', 'Jr. Los Jazmines 789, SJL', '945678912'),
        ('74567890', 'Ana', 'Fernández', 'Av. Lurigancho 1011, SJL', '978901234'),
        ('85678901', 'Luis', 'Martínez', 'Psje. Las Esmeraldas 1213, SJL', '901234567'),
        ('96789012', 'Rosa', 'Díaz', 'Calle Los Tulipanes 1415, SJL', '923456789'),
        ('67890234', 'Jorge', 'Castro', 'Jr. Los Rosales 1617, SJL', '934567890'),  # DNI cambiado
        ('78901345', 'Carmen', 'Ortiz', 'Av. Próceres 1819, SJL', '945678901'),    # DNI cambiado
        ('89012456', 'Pedro', 'Ramírez', 'Av. 13 de Enero 2021, SJL', '956789012'), # DNI cambiado
        ('90123567', 'Susana', 'Torres', 'Jr. Los Claveles 2223, SJL', '967890123'), # DNI cambiado
        ('01234678', 'Roberto', 'Silva', 'Urb. Mangomarca 2425, SJL', '978901234'),  # DNI cambiado
        ('12345789', 'Laura', 'Mendoza', 'Cda. Los Olivos 2627, SJL', '989012345'),  # DNI cambiado
        # Clientes adicionales con DNIS únicos
        ('23456890', 'Miguel', 'Rojas', 'Av. Los Próceres 303, SJL', '990123456'),
        ('34567901', 'Elena', 'Vargas', 'Jr. Las Gardenias 404, SJL', '991234567'),
        ('45678012', 'Fernando', 'Córdova', 'Psje. Los Pinos 505, SJL', '992345678'),
        ('56789123', 'Patricia', 'Salas', 'Calle Los Laureles 606, SJL', '993456789'),
        ('67890235', 'Ricardo', 'Peña', 'Av. Canto Grande 707, SJL', '994567890'),
        ('78901346', 'Gabriela', 'Quispe', 'Jr. Los Nardos 808, SJL', '995678901'),
        ('89012457', 'Héctor', 'Alvarez', 'Urb. Villa Jardín 909, SJL', '996789012'),
        ('90123568', 'Isabel', 'Torres', 'Cda. Las Magnolias 1010, SJL', '997890123'),
        ('01234679', 'Javier', 'Paredes', 'Av. 7 de Junio 1111, SJL', '998901234'),
        ('12345780', 'Katherine', 'Ruiz', 'Jr. Las Azucenas 1212, SJL', '999012345'),
        ('23456891', 'Leonardo', 'Guzmán', 'Psje. Los Girasoles 1313, SJL', '999123456'),
        ('34567902', 'Mónica', 'Reyes', 'Calle Los Claveles 1414, SJL', '999234567'),
        ('45678013', 'Nicolás', 'Morales', 'Av. Los Álamos 1515, SJL', '999345678'),
        ('56789124', 'Olivia', 'Sánchez', 'Jr. Los Lirios 1616, SJL', '999456789')
    ]
    
    for dni, nombres, apellidos, direccion, telefono in clientes_data:
        cliente = Cliente(
            dni=dni,
            nombres=nombres,
            apellidos=apellidos,
            direccion=direccion,
            telefono=telefono
        )
        db.session.add(cliente)
    
    # 3. PRODUCTOS (del script SQL Server - mueblería) con stock aumentado
    productos_data = [
        ('Sofá 3 Cuerpos', 'Sofá de 3 cuerpos en tela resistente', 850.00, 25),
        ('Sofá 2 Cuerpos', 'Sofá de 2 cuerpos ideal para espacios pequeños', 650.00, 20),
        ('Sillón Individual', 'Sillón individual cómodo y elegante', 320.00, 30),
        ('Sillón Reclinable', 'Sillón reclinable para máximo confort', 450.00, 18),
        ('Mesa de Centro Madera', 'Mesa de centro en madera de cedro', 280.00, 25),
        ('Mesa de Centro Vidrio', 'Mesa de centro con vidrio templado', 350.00, 20),
        ('Estante para TV', 'Estante para televisor de hasta 55 pulgadas', 420.00, 18),
        ('Estante Librero', 'Estante librero de 5 niveles', 220.00, 30),
        ('Cama Matrimonial', 'Cama matrimonial de madera maciza', 950.00, 12),
        ('Cama Queen Size', 'Cama queen size con cabecera tapizada', 1200.00, 10),
        ('Cama Individual', 'Cama individual juvenil con cajones', 480.00, 25),
        ('Ropero 3 Puertas', 'Ropero de melamine con 3 puertas', 680.00, 15),
        ('Ropero 6 Puertas', 'Ropero grande con 6 puertas', 950.00, 12),
        ('Ropero con Espejo', 'Ropero grande con espejo incorporado', 1100.00, 10),
        ('Cómoda Pequeña', 'Cómoda de tamaño reducido con cajones', 140.00, 30),
        ('Cómoda Grande', 'Cómoda espaciosa con múltiples compartimientos', 220.00, 25),
        ('Cómoda con Espejo', 'Cómoda con espejo ideal para dormitorio', 260.00, 20),
        ('Velador Moderno', 'Velador con cajón y lámpara incorporada', 120.00, 40),
        ('Mesa Comedor 6 Sillas', 'Mesa para 6 personas con sillas incluidas', 1500.00, 8),
        ('Mesa Comedor 4 Sillas', 'Mesa para 4 personas, ideal para familias', 950.00, 12),
        ('Silla Comedor Tapizada', 'Silla de comedor tapizada en tela premium', 95.00, 50),
        ('Silla Comedor Madera', 'Silla de comedor en madera de caoba', 75.00, 45),
        ('Buffet Moderno', 'Buffet moderno con puertas corredizas', 750.00, 15),
        ('Vitrina Cristal', 'Vitrina para vajilla con puertas de cristal', 900.00, 10),
        ('Repostero Metálico Pequeño', 'Repostero metálico pequeño para cocina', 170.00, 25),
        ('Repostero Metálico Grande', 'Repostero metálico grande y resistente', 250.00, 20),
        ('Repostero Melamine Pequeño', 'Repostero melamine pequeño con estantes', 200.00, 25),
        ('Repostero Melamine Grande', 'Repostero grande de melamine', 280.00, 18),
        ('Alacena Cocina', 'Alacena para cocina con puertas', 420.00, 15),
        ('Isla Cocina', 'Isla para cocina con espacio de almacenaje', 850.00, 10),
        ('Colchón Sueños plaza y media', 'Colchón marca Sueños para plaza y media', 320.00, 20),
        ('Colchón Dormitel plaza y media', 'Colchón Dormitel cómodo y económico', 300.00, 25),
        ('Colchón Sueños 2 plazas', 'Colchón Sueños de 2 plazas de alta durabilidad', 420.00, 18),
        ('Colchón Dormitel 2 plazas', 'Colchón Dormitel tamaño 2 plazas', 390.00, 20),
        ('Colchón Paraíso', 'Colchón Paraíso ortopédico premium', 500.00, 15),
        ('Colchón King Size', 'Colchón king size memory foam', 750.00, 12),
        ('Zapatero', 'Zapatero práctico para organizar calzado', 120.00, 35),
        ('Zapatero con Espejo', 'Zapatero vertical con espejo frontal', 180.00, 25),
        ('Estante Multiuso', 'Estante para múltiples usos domésticos', 130.00, 30),
        ('Perchero', 'Perchero de pie para ropa y accesorios', 90.00, 40),
        ('Organizador Ropa', 'Organizador de ropa con compartimientos', 150.00, 25),
        ('Cesto Ropa Sucia', 'Cesto para ropa sucia con tapa', 65.00, 45),
        ('Espejo Pared', 'Espejo para pared tamaño grande', 180.00, 25),
        ('Mesa de Noche', 'Mesa de noche con cajón y estante', 160.00, 35),
        # Productos adicionales
        ('Escritorio Ejecutivo', 'Escritorio grande con cajones y estante', 680.00, 15),
        ('Silla Ejecutiva', 'Silla ergonómica para oficina', 420.00, 20),
        ('Librero de Pared', 'Librero modular para pared', 320.00, 18),
        ('Tocador con Espejo', 'Tocador para dormitorio con espejo grande', 580.00, 12),
        ('Banco Decorativo', 'Banco para recibidor o pasillo', 220.00, 25),
        ('Porta TV Flotante', 'Porta TV moderno estilo flotante', 380.00, 15),
        ('Cuna Infantil', 'Cuna para bebé con colchón incluido', 520.00, 10),
        ('Cambiador para Bebé', 'Mueble cambiador para bebé', 280.00, 12),
        ('Barra de Cocina', 'Barra desayunadora para cocina', 650.00, 8),
        ('Estante de Baño', 'Estante para baño resistente a la humedad', 150.00, 30),
        ('Mesa Auxiliar', 'Mesa auxiliar para sala', 180.00, 25),
        ('Sillón de Exterior', 'Sillón resistente para terraza o jardín', 380.00, 15),
        ('Mesa de Exterior', 'Mesa para exterior resistente a la intemperie', 520.00, 10),
        ('Hamaca Familiar', 'Hamaca familiar para jardín', 280.00, 8),
        ('Organizador de Zapatos', 'Organizador de zapatos plegable', 85.00, 40),
        ('Cesto de Juguetes', 'Cesto grande para organizar juguetes', 75.00, 35),
        ('Estante de Cocina', 'Estante organizador para cocina', 120.00, 30),
        ('Porta Vinos', 'Porta vinos de madera con capacidad para 12 botellas', 160.00, 20),
        ('Espejo de Piso', 'Espejo de cuerpo completo con marco de madera', 320.00, 12),
        ('Armario Ropero', 'Armario ropero desmontable', 780.00, 10)
    ]
    
    for nombre, descripcion, precio, stock in productos_data:
        producto = Producto(
            nombre_producto=nombre,
            descripcion=descripcion,
            precio=precio,
            stock=stock
        )
        db.session.add(producto)
    
    try:
        db.session.commit()
    except Exception as e:
        print(f"⚠ Error al guardar datos iniciales: {e}")
        db.session.rollback()
        raise
    
    print("\n" + "="*60)
    print("SISTEMA DE VENTAS - BASE DE DATOS INICIALIZADA")
    print("="*60)
    print(f"✓ {len(usuarios_data)} usuarios creados")
    print(f"✓ {len(clientes_data)} clientes registrados")
    print(f"✓ {len(productos_data)} productos cargados")
    print(f"✓ Hora del sistema: {hora_peru()}")
    
    # Crear ventas históricas después de inicializar datos
    crear_ventas_historicas()
    
    # Estadísticas finales
    print("\n" + "="*60)
    print("ESTADÍSTICAS FINALES")
    print("="*60)
    print(f"Total Clientes: {Cliente.query.count()}")
    print(f"Total Productos: {Producto.query.count()}")
    print(f"Total Ventas: {Venta.query.count()}")
    print(f"Total Auditorías: {Auditoria.query.count()}")
    
    # Sumar total de ventas
    total_ventas = db.session.query(db.func.sum(Venta.total)).scalar() or 0
    print(f"Total en Ventas: S/. {float(total_ventas):.2f}")
    
    print("\nUSUARIOS DISPONIBLES:")
    print("1. admin / AdminSecure123 → Acceso completo")
    print("2. vendedor1 / VendedorSecure456 → Solo ventas")
    print("3. vendedor2 / VendedorSecure456 → Solo ventas")
    print("4. consulta1 / ConsultaSecure789 → Solo lectura")
    print("="*60)
    print("\n✅ Sistema listo para usar con datos de prueba realistas!")
    print("="*60)