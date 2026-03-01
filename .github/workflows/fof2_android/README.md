# foF2 Monitor — Android App

Monitor en tiempo real de foF2 y MUF(3000) de la ionosonda de Roquetes (EB040).

---

## Cómo compilar el APK (sin instalar nada en tu PC)

### Paso 1 — Crear cuenta en GitHub
Ve a https://github.com y crea una cuenta gratuita si no tienes.

### Paso 2 — Crear repositorio nuevo
1. Haz clic en **New repository**
2. Nombre: `fof2-monitor`
3. Visibilidad: **Public** (necesario para Actions gratuito)
4. Haz clic en **Create repository**

### Paso 3 — Subir los archivos
Sube estos 4 archivos al repositorio (arrastra y suelta en la web de GitHub):
```
main.py
buildozer.spec
.github/workflows/build.yml
```
> Para subir `.github/workflows/build.yml` necesitas crear la carpeta:
> en GitHub web haz clic en "Add file" → "Create new file" → escribe
> `.github/workflows/build.yml` en el nombre y pega el contenido.

### Paso 4 — Esperar la compilación
1. Ve a la pestaña **Actions** de tu repositorio
2. Verás el workflow **Build foF2 Monitor APK** ejecutándose
3. Espera ~15-25 minutos (la primera vez tarda más por las descargas)
4. Cuando aparezca ✅ verde, haz clic en el workflow

### Paso 5 — Descargar el APK
1. En la sección **Artifacts** al final de la página
2. Haz clic en **foF2-Monitor-APK** para descargar el zip
3. Extrae el zip — dentro está el archivo `.apk`

### Paso 6 — Instalar en Android
1. Copia el `.apk` a tu móvil (por USB, email, Drive, etc.)
2. En Android: **Ajustes → Seguridad → Fuentes desconocidas** → Activar
   (o en Android 8+: se pide permiso al intentar instalar)
3. Abre el `.apk` y toca **Instalar**

---

## Funcionalidades de la app

- **foF2 en tiempo real** desde FTP anónimo de Roquetes
- **MUF(3000)** leída directamente del archivo SAO
- **Color de fondo** por banda HF:
  - Negro: sin datos / < 3 MHz
  - Verde: 80m (≥ 3 MHz)
  - Amarillo: 40m inicio (≥ 5 MHz)
  - Naranja: 40m (≥ 7 MHz)
  - Rojo: 30m (≥ 10 MHz)
- **Tendencia** ↑ ↓ → comparando últimas lecturas
- **Gráfica histórica** cargada del FTP al arrancar
- **Notificación persistente** en la barra de Android
- **Alerta visual** si foF2 cambia bruscamente
- **Configuración** completa desde la app:
  - Intervalo de actualización (1-30 min)
  - Lecturas a mostrar en gráfica
  - Lecturas a precargar al arrancar
  - Umbral de alerta
  - Activar/desactivar notificaciones

---

## Actualizaciones

Para compilar una nueva versión, sube el `main.py` actualizado al repositorio.
GitHub Actions compilará automáticamente el nuevo APK.
