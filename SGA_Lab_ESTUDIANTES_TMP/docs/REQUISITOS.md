# Requisitos funcionales
RF01 Registro con documento, nombre, apellido, correo, teléfono y contraseña; correo único y válido.
RF02 Autenticación; bloqueo temporal después de cinco intentos fallidos.
RF03 Gestión de cursos: código, nombre, descripción, docente, horario, cupo y estado.
RF04 Matrícula: usuario autenticado, curso activo, cupo disponible, sin duplicados.
RF05 Cada matrícula debe disminuir el cupo; cero cupos bloquea nuevas matrículas.
RF06 Notas de 0.0 a 5.0 y definitiva como promedio de tres notas.
RF07 Estudiante solo consulta su información académica.
RF08 Reportes para roles autorizados.

# Requisitos no funcionales de laboratorio
RNF01 Rendimiento: definir umbral antes de medir.
RNF02 Seguridad: autenticación, autorización, aislamiento y contraseñas.
RNF03 Compatibilidad: navegadores y tamaños de pantalla.
RNF04 Accesibilidad: teclado, etiquetas y contraste.
RNF05 Mantenibilidad: complejidad, duplicación y claridad.
RNF06 Portabilidad: segundo entorno.
RNF07 Tolerancia: interrupciones y solicitudes repetidas.
