-- base_de_datos.sql
-- Crea todas las tablas del sistema. Se ejecuta una sola vez en el SQL Editor de Supabase.

-- 1. REQUISITOS: documentos que exige cada tipo de reclamación
create table requisitos (
  tipo_reclamacion text not null,
  documento text not null,
  primary key (tipo_reclamacion, documento)
);

insert into requisitos (tipo_reclamacion, documento) values
('muerte_natural','formato_reclamacion'),
('muerte_natural','registro_civil_defuncion'),
('muerte_natural','certificado_medico_defuncion'),
('muerte_natural','cedula_asegurado'),
('muerte_natural','cedula_beneficiario'),
('muerte_natural','sarlaft'),
('muerte_natural','certificacion_bancaria'),
('muerte_accidental','formato_reclamacion'),
('muerte_accidental','registro_civil_defuncion'),
('muerte_accidental','certificado_medico_defuncion'),
('muerte_accidental','cedula_asegurado'),
('muerte_accidental','cedula_beneficiario'),
('muerte_accidental','sarlaft'),
('muerte_accidental','certificacion_bancaria'),
('muerte_accidental','informe_autoridad'),
('incapacidad','formato_reclamacion'),
('incapacidad','dictamen_perdida_capacidad'),
('incapacidad','historia_clinica'),
('incapacidad','cedula_asegurado'),
('incapacidad','sarlaft'),
('incapacidad','certificacion_bancaria');

-- 2. ANALISTAS: usuarios del panel (se crean con crear_analista.py)
create table analistas (
  id uuid primary key default gen_random_uuid(),
  correo text unique not null,
  nombre text not null,
  contrasena_cifrada text not null,
  activo boolean not null default true,
  fecha_creacion timestamptz not null default now()
);

-- 3. CASOS: cada reclamación radicada
create table casos (
  id uuid primary key default gen_random_uuid(),
  numero_radicado text unique not null,
  codigo_seguimiento text unique not null,
  nombre_beneficiario text not null,
  documento_beneficiario text not null,
  correo_beneficiario text not null,
  telefono_beneficiario text,
  nombre_asegurado text not null,
  documento_asegurado text not null,
  relato text not null,
  tipo_sugerido_ia text check (tipo_sugerido_ia in ('muerte_natural','muerte_accidental','incapacidad')),
  confianza_ia numeric(3,2),
  explicacion_ia text,
  tipo_confirmado text check (tipo_confirmado in ('muerte_natural','muerte_accidental','incapacidad')),
  estado text not null default 'incompleto'
    check (estado in ('incompleto','completo','pagado','objetado')),
  fecha_radicacion timestamptz not null default now(),
  fecha_primera_respuesta timestamptz,
  fecha_expediente_completo timestamptz,   -- aquí arranca el plazo legal
  fecha_vencimiento date
);

-- Un beneficiario no puede tener dos casos abiertos por el mismo asegurado
create unique index unico_caso_abierto
  on casos (documento_asegurado, documento_beneficiario)
  where estado in ('incompleto','completo');

-- 4. DOCUMENTOS: archivos que sube el beneficiario
create table documentos (
  id uuid primary key default gen_random_uuid(),
  caso_id uuid not null references casos(id),
  nombre_archivo text not null,
  ubicacion_archivo text not null,
  huella_archivo text not null,
  tipo_documento text,
  estado text not null default 'pendiente' check (estado in ('pendiente','valido','invalido')),
  motivo_rechazo text,
  fecha_subida timestamptz not null default now(),
  unique (caso_id, huella_archivo)
);

-- 5. EVENTOS: historia completa de cada caso
create table eventos (
  id bigint generated always as identity primary key,
  caso_id uuid not null references casos(id),
  tipo_evento text not null,
  responsable text not null,
  detalle jsonb,
  fecha_evento timestamptz not null default now()
);

-- 6. DECISIONES: lo que decide el analista
create table decisiones (
  id bigint generated always as identity primary key,
  caso_id uuid not null references casos(id),
  analista_id uuid not null references analistas(id),
  decision text not null check (decision in ('pagar','objetar','pedir_documentos')),
  comentario text not null,
  fecha_decision timestamptz not null default now()
);

-- 7. ALERTAS: avisos de riesgo o vencimiento (una sola vez por caso y nivel)
create table alertas (
  id bigint generated always as identity primary key,
  caso_id uuid not null references casos(id),
  nivel text not null check (nivel in ('riesgo','vencido')),
  fecha_envio timestamptz not null default now(),
  unique (caso_id, nivel)
);

-- 8. EJECUCIONES: registro de cada vez que corre la vigilancia automática
create table ejecuciones (
  id bigint generated always as identity primary key,
  tarea text not null,
  inicio timestamptz not null,
  fin timestamptz not null,
  exitosa boolean not null,
  resultado jsonb
);
