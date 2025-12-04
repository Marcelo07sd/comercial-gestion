# app.py - Sistema de Ventas con Login y Permisos
import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from functools import wraps
from datetime import datetime

from models import (db, Cliente, Usuario, Producto, Venta, DetalleVenta, 
                    Auditoria, registrar_venta, inicializar_datos)

app = Flask(__name__)

# ===== CONFIGURACIÓN =====

raw_database_url = os.environ.get(
    'DATABASE_URL',
    'sqlite:///sistema_ventas.db'  # fallback local
)

# Render entrega postgres:// pero SQLAlchemy requiere postgresql://
if raw_database_url.startswith("postgres://"):
    raw_database_url = raw_database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = raw_database_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor inicie sesión para acceder a esta página.'

with app.app_context():
    inicializar_datos()


# ===== FLASK-LOGIN =====

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


# ===== DECORADOR DE PERMISOS =====

def requiere_permiso(accion):
    """Decorador para verificar permisos según rol"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Debe iniciar sesión', 'warning')
                return redirect(url_for('login'))
            
            if not current_user.tiene_permiso(accion):
                flash(f'No tiene permisos para: {accion}', 'danger')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ===== RUTAS DE AUTENTICACIÓN =====

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Inicio de sesión"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        usuario = Usuario.query.filter_by(username=username).first()
        
        if usuario and usuario.activo and usuario.check_password(password):
            login_user(usuario, remember=request.form.get('remember', False))
            flash(f'Bienvenido {usuario.nombre_completo}', 'success')
            
            # Registrar auditoría
            auditoria = Auditoria(
                tabla='Usuario',
                accion='LOGIN',
                id_registro=usuario.id_usuario,
                usuario_sql=usuario.username,
                datos=f'Inicio de sesión exitoso'
            )
            db.session.add(auditoria)
            db.session.commit()
            
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """Cerrar sesión"""
    auditoria = Auditoria(
        tabla='Usuario',
        accion='LOGOUT',
        id_registro=current_user.id_usuario,
        usuario_sql=current_user.username,
        datos='Cierre de sesión'
    )
    db.session.add(auditoria)
    db.session.commit()
    
    logout_user()
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('login'))


# ===== RUTAS PRINCIPALES =====

@app.route('/')
@login_required
def index():
    """Panel principal"""
    # Estadísticas básicas
    stats = {
        'total_clientes': Cliente.query.count(),
        'total_productos': Producto.query.count(),
        'total_ventas': Venta.query.count(),
        'productos_bajo_stock': Producto.query.filter(Producto.stock <= 10).count()
    }
    return render_template('index.html', stats=stats)


# ===== GESTIÓN DE CLIENTES =====

@app.route('/clientes')
@login_required
@requiere_permiso('leer')
def ver_clientes():
    """Lista todos los clientes"""
    clientes = Cliente.query.all()
    return render_template('ver_clientes.html', clientes=clientes)


@app.route('/clientes/nuevo', methods=['GET', 'POST'])
@login_required
@requiere_permiso('crear')
def nuevo_cliente():
    """Registra un nuevo cliente"""
    if request.method == 'POST':
        dni = request.form['dni']
        
        if Cliente.query.filter_by(dni=dni).first():
            flash('El DNI ya está registrado', 'danger')
            return redirect(url_for('nuevo_cliente'))
        
        cliente = Cliente(
            dni=dni,
            nombres=request.form['nombres'],
            apellidos=request.form['apellidos'],
            direccion=request.form.get('direccion'),
            telefono=request.form.get('telefono')
        )
        
        db.session.add(cliente)
        
        # Auditoría
        auditoria = Auditoria(
            tabla='Cliente',
            accion='INSERT',
            id_registro=cliente.id_cliente,
            usuario_sql=current_user.username,
            datos=f'Cliente: {cliente.nombres} {cliente.apellidos}'
        )
        db.session.add(auditoria)
        
        db.session.commit()
        flash('Cliente registrado exitosamente', 'success')
        return redirect(url_for('ver_clientes'))
    
    return render_template('nuevo_cliente.html')


@app.route('/clientes/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@requiere_permiso('actualizar')
def editar_cliente(id):
    """Edita un cliente existente"""
    cliente = Cliente.query.get_or_404(id)
    
    if request.method == 'POST':
        dni = request.form['dni']
        
        # Verificar DNI único
        if dni != cliente.dni and Cliente.query.filter_by(dni=dni).first():
            flash('El DNI ya está registrado por otro cliente', 'danger')
            return redirect(url_for('editar_cliente', id=id))
        
        cliente.dni = dni
        cliente.nombres = request.form['nombres']
        cliente.apellidos = request.form['apellidos']
        cliente.direccion = request.form.get('direccion')
        cliente.telefono = request.form.get('telefono')
        
        # Auditoría
        auditoria = Auditoria(
            tabla='Cliente',
            accion='UPDATE',
            id_registro=cliente.id_cliente,
            usuario_sql=current_user.username,
            datos=f'Cliente actualizado: {cliente.nombres} {cliente.apellidos}'
        )
        db.session.add(auditoria)
        
        db.session.commit()
        flash('Cliente actualizado correctamente', 'success')
        return redirect(url_for('ver_clientes'))
    
    return render_template('editar_cliente.html', cliente=cliente)


@app.route('/clientes/<int:id>/eliminar', methods=['POST'])
@login_required
@requiere_permiso('eliminar')
def eliminar_cliente(id):
    """Elimina un cliente si no tiene ventas"""
    cliente = Cliente.query.get_or_404(id)
    
    if Venta.query.filter_by(id_cliente=cliente.id_cliente).count() > 0:
        flash('No se puede eliminar. El cliente tiene ventas registradas', 'danger')
        return redirect(url_for('ver_clientes'))
    
    # Auditoría
    auditoria = Auditoria(
        tabla='Cliente',
        accion='DELETE',
        id_registro=cliente.id_cliente,
        usuario_sql=current_user.username,
        datos=f'Cliente eliminado: {cliente.nombres} {cliente.apellidos}'
    )
    db.session.add(auditoria)
    
    db.session.delete(cliente)
    db.session.commit()
    flash('Cliente eliminado correctamente', 'success')
    return redirect(url_for('ver_clientes'))


# ===== GESTIÓN DE PRODUCTOS =====

@app.route('/productos')
@login_required
@requiere_permiso('leer')
def ver_productos():
    """Lista todos los productos"""
    productos = Producto.query.all()
    return render_template('productos.html', productos=productos)


@app.route('/productos/nuevo', methods=['GET', 'POST'])
@login_required
@requiere_permiso('crear')
def nuevo_producto():
    """Registra un nuevo producto"""
    if request.method == 'POST':
        producto = Producto(
            nombre_producto=request.form['nombre_producto'],
            descripcion=request.form['descripcion'],
            precio=float(request.form['precio']),
            stock=int(request.form['stock'])
        )
        db.session.add(producto)
        db.session.commit()
        flash('Producto registrado exitosamente', 'success')
        return redirect(url_for('ver_productos'))
    
    return render_template('nuevo_producto.html')


@app.route('/productos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@requiere_permiso('actualizar')
def editar_producto(id):
    """Edita un producto existente"""
    producto = Producto.query.get_or_404(id)
    
    if request.method == 'POST':
        producto.nombre_producto = request.form['nombre_producto']
        producto.descripcion = request.form['descripcion']
        producto.precio = float(request.form['precio'])
        producto.stock = int(request.form['stock'])
        db.session.commit()
        flash('Producto actualizado correctamente', 'success')
        return redirect(url_for('ver_productos'))
    
    return render_template('editar_producto.html', producto=producto)


@app.route('/productos/<int:id>/eliminar', methods=['POST'])
@login_required
@requiere_permiso('eliminar')
def eliminar_producto(id):
    """Elimina un producto"""
    producto = Producto.query.get_or_404(id)
    
    # Verificar si tiene detalles de venta
    if DetalleVenta.query.filter_by(id_producto=producto.id_producto).count() > 0:
        flash('No se puede eliminar. El producto tiene ventas registradas', 'danger')
        return redirect(url_for('ver_productos'))
    
    db.session.delete(producto)
    db.session.commit()
    flash('Producto eliminado correctamente', 'success')
    return redirect(url_for('ver_productos'))


# ===== GESTIÓN DE VENTAS =====

@app.route('/ventas')
@login_required
@requiere_permiso('ventas')
def ver_ventas():
    """Lista todas las ventas"""
    ventas = Venta.query.order_by(Venta.fecha_venta.desc()).all()
    return render_template('ventas.html', ventas=ventas)


@app.route('/ventas/nueva', methods=['GET', 'POST'])
@login_required
@requiere_permiso('ventas')
def nueva_venta():
    """Registra una nueva venta"""
    if request.method == 'POST':
        id_cliente = int(request.form['id_cliente'])
        fecha = datetime.now().date()
        
        # Obtener detalles de productos
        detalles = []
        productos_ids = request.form.getlist('id_producto')
        cantidades = request.form.getlist('cantidad')
        
        for i in range(len(productos_ids)):
            id_producto = int(productos_ids[i])
            cantidad = int(cantidades[i])
            
            if cantidad <= 0:
                continue
            
            producto = Producto.query.get(id_producto)
            if producto:
                detalles.append({
                    'id_producto': id_producto,
                    'cant': cantidad,
                    'precio': float(producto.precio)
                })
        
        if not detalles:
            flash('Debe agregar al menos un producto', 'warning')
            return redirect(url_for('nueva_venta'))
        
        # Registrar venta
        resultado = registrar_venta(
            id_cliente=id_cliente,
            id_usuario=current_user.id_usuario,
            fecha=fecha,
            detalles_productos=detalles
        )
        
        if resultado['status'] == 'success':
            flash(resultado['mensaje'], 'success')
            return redirect(url_for('detalle_venta', id=resultado['venta_id']))
        else:
            flash(resultado['mensaje'], 'danger')
            return redirect(url_for('nueva_venta'))
    
    # GET
    clientes = Cliente.query.all()
    productos = Producto.query.filter(Producto.stock > 0).all()
    return render_template('nueva_venta.html', clientes=clientes, productos=productos)


@app.route('/ventas/<int:id>')
@login_required
@requiere_permiso('leer')
def detalle_venta(id):
    """Muestra el detalle de una venta"""
    venta = Venta.query.get_or_404(id)
    return render_template('detalle_venta.html', venta=venta)


# ===== API ENDPOINTS =====

@app.route('/api/productos/<int:id>')
@login_required
def api_producto(id):
    """API: Obtener información de un producto"""
    producto = Producto.query.get_or_404(id)
    return jsonify({
        'id_producto': producto.id_producto,
        'nombre_producto': producto.nombre_producto,
        'precio': float(producto.precio),
        'stock': producto.stock
    })


# ===== REPORTES =====

@app.route('/reportes')
@login_required
@requiere_permiso('reportes')
def reportes():
    """Panel de reportes"""
    # Ventas por vendedor
    from sqlalchemy import func
    
    ventas_por_vendedor = db.session.query(
        Usuario.nombre_completo,
        func.count(Venta.id_venta).label('total_ventas'),
        func.sum(Venta.total).label('monto_total')
    ).join(Venta).group_by(Usuario.nombre_completo).all()
    
    # Productos más vendidos
    productos_vendidos = db.session.query(
        Producto.nombre_producto,
        func.sum(DetalleVenta.cantidad).label('total_vendido')
    ).join(DetalleVenta).group_by(Producto.nombre_producto)\
     .order_by(func.sum(DetalleVenta.cantidad).desc()).limit(10).all()
    
    # Productos con stock bajo
    productos_bajo_stock = Producto.query.filter(Producto.stock <= 10)\
                                         .order_by(Producto.stock).all()
    
    return render_template('reportes.html',
                         ventas_por_vendedor=ventas_por_vendedor,
                         productos_vendidos=productos_vendidos,
                         productos_bajo_stock=productos_bajo_stock)


@app.route('/auditoria')
@login_required
@requiere_permiso('reportes')
def ver_auditoria():
    """Muestra el registro de auditoría"""
    auditorias = Auditoria.query.order_by(Auditoria.fecha.desc()).limit(100).all()
    return render_template('auditoria.html', auditorias=auditorias)


# ===== CONTEXTO DE PLANTILLAS =====

@app.context_processor
def inject_user():
    """Inyecta información del usuario en todas las plantillas"""
    return dict(current_user=current_user)


# ===== MANEJO DE ERRORES =====

@app.errorhandler(403)
def forbidden(e):
    flash('No tiene permisos para acceder a esta página', 'danger')
    return redirect(url_for('index'))


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(e):
    db.session.rollback()
    return render_template('500.html'), 500


# ===== EJECUTAR APLICACIÓN =====
