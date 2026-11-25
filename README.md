# Radicación de reclamaciones de seguros de vida

Prueba técnica para la vacante 631 (Desarrollador Junior IA y Automatización).
Miguel Ángel Gómez Hernández, Ingeniero de Sistemas y Computación.

Este proyecto recibe reclamaciones de seguros de vida, identifica con IA de qué tipo son, revisa si el expediente está completo y lleva solo el control del plazo de un mes del artículo 1080 del Código de Comercio. La decisión de pagar, objetar o pedir documentos siempre la toma una persona.

## Enlaces

- Formulario de radicación: https://radicacion-seguros.onrender.com
- Panel del analista: https://radicacion-seguros.onrender.com/panel
- Indicadores (punto 7): https://radicacion-seguros.onrender.com/panel/indicadores
- Estado del sistema: https://radicacion-seguros.onrender.com/salud

Usuario de prueba para el panel:

- Correo: `evaluadorprueba@gmail.com`
- Contraseña: `Evaluador2026**Admin`

Nota: está en el plan gratuito de Render, que apaga la app cuando nadie la usa. Si la primera carga tarda cerca de un minuto, es por eso. Dejé un monitor que la visita cada 5 minutos para que casi siempre esté despierta.

## Cómo funciona

El beneficiario llena un formulario web, cuenta qué pasó y sube sus documentos. No necesita crear usuario. Al terminar recibe un número de radicado y un enlace de seguimiento donde ve qué le falta y puede enviarlo después.

Con cada radicación, el sistema hace lo siguiente en segundo plano:

1. La IA (Gemini) lee cada documento y dice qué es, si se lee bien, si tiene firma y a qué cédula pertenece.
2. Con eso, el código decide si el documento sirve. Por ejemplo, compara la cédula con la del asegurado.
3. La IA lee el relato y sugiere el tipo de reclamación, con su nivel de confianza y en qué se basó.
4. El código compara lo recibido con los documentos que exige ese tipo y saca la lista de lo que falta.
5. Si no falta nada, empieza a contar el plazo y calcula la fecha de vencimiento.

Separé las cosas así a propósito: la IA solo mira y sugiere, y las reglas deciden. Así la IA no puede dar por completo un expediente ni decidir un pago, y el mensaje que recibe el beneficiario lo arma el código, no la IA.

El analista entra al panel con usuario y contraseña. Ahí ve los casos abiertos, en qué día del plazo va cada uno, qué sugirió la IA y con qué información, y la historia completa del caso. Desde ahí confirma o corrige el tipo y registra su decisión, que queda a su nombre.

Cada hora, GitHub Actions llama a una tarea que reintenta los documentos que la IA no alcanzó a revisar y genera alertas cuando un caso entra en riesgo o se vence. Además, UptimeRobot revisa `/salud` cada 5 minutos y me avisa por correo si algo falla.

## Archivos principales

- `main.py`: rutas públicas (formulario, seguimiento, tarea automática y salud).
- `radicacion.py`: recibe, valida y guarda la radicación sin duplicarla.
- `motor.py`: reglas del negocio y reloj legal.
- `ia.py`: lo único que habla con el modelo de IA. Si se cambia de modelo, solo se toca este archivo.
- `plazos.py`: calcula el día del plazo y si el caso está en tiempo, en riesgo o vencido.
- `panel.py`: panel del analista, login, decisiones e indicadores.
- `vigilancia.py`: la tarea automática de cada hora.
- `config.py`: lee las claves y crea las conexiones.
- `crear_analista.py`: crea usuarios del panel.
- `base_de_datos.sql`: crea todas las tablas.
- `datos_prueba/`: las 32 radicaciones de prueba y los scripts para cargarlas y revisarlas.
- `.github/workflows/vigilar.yml`: el reloj automático.

## Cómo levantarlo desde cero

Se necesita Python 3.12, Git, una cuenta gratis en Supabase y una clave gratis de Google AI Studio.

**1. Base de datos**

1. Crear un proyecto en Supabase.
2. En SQL Editor, ejecutar todo `base_de_datos.sql`.
3. En Storage, crear un bucket privado llamado `documentos`, con límite de 10 MB y tipos `application/pdf, image/jpeg, image/png`.
4. En Project Settings → API Keys, copiar la URL del proyecto y la Secret key.

**2. Código**

```bash
git clone https://github.com/Angel-gh11/Radicacion-seguros.git
cd Radicacion-seguros
python -m venv venv
venv\Scripts\activate          # en Mac o Linux: source venv/bin/activate
pip install -r requirements.txt
```

**3. Claves**

Copiar `.env.ejemplo` como `.env` y llenarlo. Para `CLAVE_SESION` y `TOKEN_TAREAS` se genera un valor distinto para cada una con:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Con `python prueba_conexion.py` se puede comprobar que la base de datos y la IA responden.

**4. Usuario del panel**

```bash
python crear_analista.py
```

**5. Ejecutar**

```bash
uvicorn main:app --reload
```

El formulario queda en http://127.0.0.1:8000 y el panel en http://127.0.0.1:8000/panel.

**6. Datos de prueba (opcional)**

Con el servidor encendido, en otra terminal:

```bash
python datos_prueba/cargar.py          # envía las 32 radicaciones (tarda unos 15 minutos)
python datos_prueba/simular_tiempo.py  # adelanta el reloj de 4 casos para ver alertas
python datos_prueba/verificar.py       # compara lo esperado con lo que hizo el sistema
```

La vigilancia también se puede correr a mano:

```bash
curl -X POST -H "X-Token-Tareas: TU_TOKEN" http://127.0.0.1:8000/tareas/vigilar
```

## Despliegue

Lo publiqué en Render como Web Service gratuito, en la región de Ohio porque ahí está la base de datos.

- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Variables de entorno: las mismas del `.env` más `PYTHON_VERSION=3.12.4`.

Para el reloj automático hay que crear en GitHub (Settings → Secrets and variables → Actions) los secretos `URL_APP` y `TOKEN_TAREAS`, este último igual al de Render.

Para el monitoreo usé un monitor HTTP de UptimeRobot sobre `/salud` cada 5 minutos, con aviso por correo.

## Las cuatro preguntas del punto 7

Están en `/panel/indicadores` y se calculan con los datos de la base cada vez que se abre la página. También se pueden sacar directo desde el SQL Editor de Supabase:

```sql
-- 1. Casos abiertos, día del plazo, en riesgo y vencidos
select numero_radicado, estado, fecha_vencimiento,
  case
    when fecha_expediente_completo is null then 'sin iniciar'
    when (now() at time zone 'America/Bogota')::date > fecha_vencimiento then 'vencido'
    when fecha_vencimiento - (now() at time zone 'America/Bogota')::date <= 7 then 'en riesgo'
    else 'en tiempo'
  end as semaforo,
  (now() at time zone 'America/Bogota')::date
    - (fecha_expediente_completo at time zone 'America/Bogota')::date + 1 as dia_del_plazo
from casos
where estado in ('incompleto', 'completo')
order by fecha_vencimiento nulls last;

-- 2. Clasificaciones de la IA corregidas por una persona
select count(*) filter (where tipo_confirmado is not null) as confirmadas,
       count(*) filter (where tipo_confirmado <> tipo_sugerido_ia) as corregidas
from casos;

-- 3. Minutos desde la radicación hasta decirle al beneficiario qué le falta
select round(avg(extract(epoch from fecha_primera_respuesta - fecha_radicacion)) / 60, 1) as promedio_minutos,
       round(max(extract(epoch from fecha_primera_respuesta - fecha_radicacion)) / 60, 1) as maximo_minutos
from casos
where fecha_primera_respuesta is not null;

-- 4. Historia completa de un caso
select fecha_evento, tipo_evento, responsable, detalle
from eventos
where caso_id = (select id from casos where numero_radicado = 'RAD-XXXXXXXX-XXXXXX')
order by fecha_evento;
```

En el panel también hay un botón que abre un caso al azar con toda su historia.

## Decisiones que tomé

- **Canal web.** Quien radica acaba de perder a un familiar. Con una página no tiene que instalar nada ni crear cuenta, y subir fotos o PDF desde el celular es fácil.
- **Enlace de seguimiento.** La conversación no termina al radicar: con ese enlace el beneficiario ve qué le falta y lo envía cuando lo tenga.
- **El plazo arranca cuando el expediente queda completo**, no en la primera radicación. Por eso hay una fecha aparte para eso (`fecha_expediente_completo`).
- **Duplicados bloqueados desde la base de datos.** Cada archivo tiene una huella única y no puede haber dos casos abiertos para el mismo asegurado y beneficiario. Funciona aunque lleguen dos envíos al mismo tiempo, y un reenvío no reinicia el plazo.
- **Historia de cada caso.** Todo lo que pasa queda en la tabla `eventos`: qué llegó, qué dijo la IA, qué decidieron las reglas, qué hizo el analista y cuándo.
- **Qué pasa si la IA falla.** Reintenta, prueba con un modelo de respaldo y, si nada funciona, clasifica por palabras clave con confianza baja para que el analista lo revise. Los documentos quedan pendientes y la tarea de cada hora los vuelve a intentar. Esto me pasó de verdad durante las pruebas, porque Gemini respondió con error 503 por saturación.
- **El reloj se dispara desde afuera.** Render apaga la app cuando no hay visitas, así que un reloj interno se apagaría con ella. GitHub Actions la despierta cada hora y me avisa si falla.

## Seguridad

En el formulario público:

- Se revisa el contenido real del archivo, no solo la extensión. Solo entra PDF, JPG o PNG, máximo 10 MB por archivo y 15 por envío.
- Los archivos quedan en un bucket privado. Solo se abren desde el panel, con enlaces que vencen en 5 minutos.
- Si alguien radica con dos cédulas que ya tienen un caso abierto, no se le muestra ese caso.
- El relato se le pasa a la IA como información y no como instrucciones. En los datos de prueba hay un caso que intenta manipularla y no lo logra.
- Se pide autorización de tratamiento de datos (Ley 1581 de 2012).

En el panel:

- Contraseñas cifradas con bcrypt y bloqueo de 15 minutos después de 5 intentos fallidos.
- Sesión firmada que dura máximo 8 horas y en internet solo viaja por HTTPS.
- No hay registro abierto: los usuarios se crean con un script.

Las claves están solo en el `.env` local, en Render y en los secretos de GitHub. Además, todas las tablas tienen RLS activo, así que con la clave pública no se puede leer nada.

## Supuestos

Como el enunciado no lo dice, asumí esto:

1. "Un mes" es un mes calendario: del 20 de octubre al 20 de noviembre. Si ese día no existe en el mes siguiente, se usa el último día del mes. No descuento fines de semana ni festivos.
2. Un caso está en riesgo cuando le quedan 7 días o menos.
3. Si el analista pide más documentos con el expediente ya completo, el plazo no se reinicia.
4. Cada beneficiario tiene un solo caso abierto por asegurado. Si hay varios beneficiarios, son casos separados.
5. En incapacidad, normalmente reclama el mismo asegurado.
6. El sistema no calcula la indemnización ni los intereses de mora.

## Preguntas que haría

1. ¿El mes del artículo 1080 se cuenta en días calendario? ¿Qué pasa si vence un domingo o un festivo?
2. Si hay varios beneficiarios, ¿es un solo expediente o uno por cada uno?
3. ¿Qué pasa si el beneficiario es menor de edad?
4. ¿Las alertas le deben llegar al analista del caso, a un líder o a los dos?
5. Si se piden más documentos con el expediente ya completo, ¿se reinicia el plazo?

## Lo que dejé por fuera

- **Correos al beneficiario.** Para enviar a cualquier dirección se necesita un dominio verificado. Por ahora el enlace de seguimiento cumple esa función.
- **WhatsApp.** Preferí dejar un canal bien hecho. El motor no depende del canal, así que se puede agregar después sin tocarlo.
- **Roles en el panel.** Hoy todos los usuarios son analistas. Un rol de líder sería lo siguiente.
- **Festivos en el plazo.** Depende de la respuesta a la primera pregunta.
- **Pruebas unitarias.** Validé con las 32 radicaciones y `verificar.py`. Lo primero que agregaría son pruebas de `plazos.py` y `motor.py`.
- **Límite de envíos en el formulario.** Hoy solo el login tiene límite. En producción le pondría un captcha.

## Cómo llevarlo a Azure

- Render → Azure App Service.
- Supabase (base de datos) → Azure Database for PostgreSQL. El mismo `base_de_datos.sql` sirve.
- Supabase Storage → Azure Blob Storage, con contenedor privado y enlaces SAS de corta duración.
- Gemini → Azure OpenAI. Solo cambia `ia.py`.
- GitHub Actions → Azure Functions con Timer Trigger (o se deja GitHub Actions).
- UptimeRobot → Application Insights con pruebas de disponibilidad.
- Variables de entorno → Azure Key Vault.

Para hacerlo necesitaría una suscripción de Azure, un recurso de Azure OpenAI aprobado y saber qué políticas de red e identidad usa la compañía, por ejemplo si el panel debe entrar con Microsoft Entra ID.

## Uso de inteligencia artificial

Me apoyé en IA como asistente durante el desarrollo, para concretar ideas, resolver errores y agilizar la escritura del código y los documentos de prueba. Las decisiones de diseño, la configuración, las pruebas y la revisión de cada parte las hice yo.

## Datos de prueba

Los detalles están en `datos_prueba/LEEME.md`. Son 30 casos distintos y 2 envíos repetidos, con documentos ficticios marcados como "MUESTRA - DATOS FICTICIOS". En la última verificación, la IA acertó el tipo en los 30 casos, los envíos repetidos no crearon casos nuevos y la vigilancia generó las alertas esperadas.

Ese 100 % hay que tomarlo con cuidado: los documentos de prueba son limpios y los relatos son claros. Con documentos reales el porcentaje va a bajar, y por eso el tipo siempre lo confirma una persona y el panel mide cuántas veces se corrige a la IA.
